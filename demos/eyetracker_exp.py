import sys
sys.path.append('exptools2')
from session import Session
from trial import Trial
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

        for trial_nr in range(self.n_trials):

            trial = TestTrial(
                session=self,
                trial_nr=trial_nr,
                phase_durations=(0.5, 0.5),
                verbose=True
            )

            trial.run()
        self.close()


if __name__ == '__main__':

    session = TestEyetrackerSession(eyetracker_on=True, n_trials=10)
    session.run()