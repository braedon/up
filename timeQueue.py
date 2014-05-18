from threading import Thread, Condition
import time
import logging

log = logging.getLogger(__name__)


class TimeQueue(Thread):

    '''
    A queue of actions to be performed at a specified time.

    Each action has a time to be executed, a function to call, and the arguments
    to call it with. When an action's time has come, it will be added to the
    provided work queue for execution.

    Once instantiated, start() should be called.
    '''

    def __init__(self, workQueue, lock=None):
        '''
        workQueue - the WorkQueue to submit actions to.

        lock - a lock to be used to synchronise access to the queue. If none
        is specified, a new lock will be created automatically.
        '''

        Thread.__init__(self)

        self.doShutdown = False

        self.workQueue = workQueue

        self.__actions = []

        # This condition variable is used to synchronise access, and wake the
        # thread when deadlines have changed.
        self.cv = Condition(lock)

    def addAction(self, executeTime, function, *args, **kwargs):
        with self.cv:
            action = (function, args, kwargs)

            log.debug('Adding action %s', action)

            self.__actions.append((executeTime, action))
            # Resort the action list, and notify anyone waiting that the
            # deadlines may have changed.
            self.__actions.sort()
            self.cv.notifyAll()
            log.debug('Time for action %s set to %d', action, executeTime)

    def shutdown(self):
        with self.cv:
            self.doShutdown = True
            self.cv.notifyAll()

    def run(self):
        while not self.doShutdown:
            # Acquire the condition before checking the actions, so that they
            # can't be modified between us checking and acting.
            with self.cv:
                if len(self.__actions) > 0:
                    (executeTime, action) = self.__actions[0]
                    # If the closest action has been reached call the handler.
                    if executeTime < time.time():
                        log.debug('Time %s for action %s passed. Executing.',
                                  executeTime, action)
                        del self.__actions[0]
                        (function, args, kwargs) = action
                        self.workQueue.submitJob(0, function, *args, **kwargs)

                    # Otherwise, go to sleep but set an alarm to wake up when
                    # the first action is up. Will be woken if the deadline
                    # list is modified.
                    else:
                        self.cv.wait(executeTime - time.time())

                # If no currently managed actions, sleep indefinitely, only to be
                # woken if the action list is modified.
                else:
                    self.cv.wait()
