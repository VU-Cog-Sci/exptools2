from exptools2.session import EyeTrackerSession
from exptools2.trial import Trial
from psychopy.visual import TextStim
from simple_exp import TestTrial


class TestEyetrackerSession(EyeTrackerSession):
    """ Simple session with x trials. """

    def __init__(self, output_str, settings_file=None, n_trials=10, eyetracker_on=True):
        """ Initializes TestSession object. """
        self.n_trials = n_trials
        super().__init__(output_str, settings_file, eyetracker_on)

    def create_trials(self, durations=(.5, .5), timing='seconds'):
        self.trials = []
        for trial_nr in range(self.n_trials):
            self.trials.append(
                TestTrial(session=self,
                          trial_nr=trial_nr,
                          phase_durations=durations,
                          txt='Trial %i' % trial_nr,
                          verbose=False,
                          timing=timing)
            )

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