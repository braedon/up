from threading import Thread, RLock
from queue import Empty, PriorityQueue
import logging

log = logging.getLogger(__name__)

# TODO: Document!


class WorkQueue(PriorityQueue):

    def __init__(self, maxsize=0, prefsize=5, maxthreads=20, minthreads=1):
        PriorityQueue.__init__(self, maxsize)
        self.threadLock = RLock()
        self.threads = []
        self.prefsize = prefsize
        self.maxthreads = maxthreads
        self.minthreads = minthreads

        for _ in range(minthreads):
            self.__createThread()

    def __createThread(self):
        with self.threadLock:
            log.debug('Creating new worker thread')
            thread = WorkThread(self)
            self.threads.append(thread)

    def __deleteThread(self):
        with self.threadLock:
            log.debug('Deleting worker thread')
            thread = self.threads[0]
            self.threads = self.threads[1:]
            thread.shutdown()

    def __adjustThreadNum(self):
        with self.threadLock:
            log.debug('%d in queue, %d threads.', self.qsize(),
                      len(self.threads))
            if len(self.threads) < self.maxthreads and \
                    self.qsize() >= self.prefsize:
                self.__createThread()
            elif len(self.threads) > self.minthreads and \
                    self.qsize() < self.prefsize:
                self.__deleteThread()

    def task_done(self):
        log.debug('Job Done')
        PriorityQueue.task_done(self)

    def submitJob(self, priority, function, *args, **kwargs):
        log.debug('Job Submitted')
        self.put((priority, function, args, kwargs))
        self.__adjustThreadNum()

    def shutdown(self):
        for thread in self.threads:
            thread.shutdown()

        for thread in self.threads:
            thread.join(3)


class WorkThread(Thread):

    def __init__(self, workQueue):
        Thread.__init__(self)
        self.workQueue = workQueue
        self.doShutdown = False
        self.daemon = True
        self.start()

    def run(self):
        while not self.doShutdown:
            try:
                _, function, args, kwargs = self.workQueue.get(True, 1)
                try:
                    log.debug('Attempting Job')
                    function(*args, **kwargs)
                except Exception:
                    log.exception('Job failed')
                self.workQueue.task_done()
            except Empty:
                pass

    def shutdown(self):
        self.doShutdown = True
