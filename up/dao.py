from collections import namedtuple
from datetime import timezone


Job = namedtuple('Job', ['job_id',
                         'status',
                         'run_dt',
                         'email',
                         'url',
                         'tries',
                         'delay_s'])


def build_insert_stmt(table, columns):
    columns_stmt = ', '.join(f'`{c}`' for c in columns)
    values_stmt = ', '.join(f'%({c})s' for c in columns)
    return f'INSERT INTO `{table}` ({columns_stmt}) VALUES ({values_stmt});'


def job_to_db_format(job):
    return job._asdict()


def job_from_db_format(db_format_job):
    # Filter DB fields to only those in our namedtuple, in case the DB has more.
    db_format_job = {k: v
                     for k, v in db_format_job.items()
                     if k in Job._fields}

    db_format_job['run_dt'] = db_format_job['run_dt'].replace(tzinfo=timezone.utc)

    return Job(**db_format_job)


def create_db(conn, db_name):
    sql = (
        f'CREATE DATABASE IF NOT EXISTS `{db_name}` '
        'CHARACTER SET `utf8mb4`'
        ';'
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)

        conn.commit()

    finally:
        conn.close()


class UpDao(object):

    def __init__(self, connection_pool):
        self.connection_pool = connection_pool

    def create_job_table(self):
        conn = self.connection_pool.connection()
        try:
            with conn.cursor() as cursor:
                sql = (
                    'CREATE TABLE IF NOT EXISTS `job` ('
                    '   `job_id` VARCHAR(100) BINARY NOT NULL,'
                    '   `status` ENUM(\'pending\', \'done\') NOT NULL,'
                    '   `run_dt` DATETIME NOT NULL,'
                    '   `email` VARCHAR(191) BINARY NOT NULL,'
                    '   `url` VARCHAR(2000) NOT NULL,'
                    '   `tries` TINYINT UNSIGNED NOT NULL,'
                    '   `delay_s` MEDIUMINT UNSIGNED NOT NULL,'
                    '   PRIMARY KEY (`job_id`),'
                    '   KEY `idx_job_status_run_dt` (`status`, `run_dt`)'
                    ');'
                )
                cursor.execute(sql)

            conn.commit()

        finally:
            conn.close()

    def insert_job(self, job):
        job_dict = job_to_db_format(job)
        sql = build_insert_stmt('job', job._fields)

        conn = self.connection_pool.connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, job_dict)

            conn.commit()

        finally:
            conn.close()

    def find_next_job(self):
        sql = 'SELECT * FROM `job`'
        sql += ' WHERE `status`=\'pending\''
        sql += ' ORDER BY `run_dt` ASC'
        sql += ' LIMIT 1'
        sql += ';'

        conn = self.connection_pool.connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                job_dicts = cursor.fetchall()
                assert len(job_dicts) in (0, 1)

        finally:
            conn.close()

        if job_dicts:
            return job_from_db_format(job_dicts[0])
        else:
            return None

    def finish_job(self, job_id, new_job=None):
        sql = 'UPDATE `job`'
        sql += ' SET `status`=\'done\''
        sql += ' WHERE `job_id`=%(job_id)s'
        sql += ';'

        sql_params = {'job_id': job_id}

        if new_job is not None:
            new_job_dict = job_to_db_format(new_job)
            new_job_sql = build_insert_stmt('job', new_job._fields)

        conn = self.connection_pool.connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, sql_params)
                assert cursor.rowcount == 1

                if new_job is not None:
                    cursor.execute(new_job_sql, new_job_dict)

            conn.commit()

        finally:
            conn.close()
