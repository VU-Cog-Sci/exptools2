from exptools2.session import Session
from exptools2.trial import Trial
from psychopy.visual import TextStim
from simple_exp import TestTrial, TestSession


class TestEyetrackerSession(TestSession):
    """ Simple session with x trials. """

    def run(self):
        """ Runs experiment. """

        self.init_eyetracker()
        self.calibrate_eyetracker()
        self.start_recording_eyetracker()
        self.start_experiment()

        for trial in self.trials:
            trial.run()
        self.close()


if __name__ == '__main__':

    session = TestEyetrackerSession('sub-01', eyetracker_on=True, n_trials=10)
    session.create_trials()
    session.run()