import sys
sys.path.append('exptools2')
from session import Session
from trial import Trial
from psychopy.visual import TextStim
from simple_exp import TestTrial, TestSession


class TestFMRISession(TestSession):
    """ Simple session with x trials. """

    def run(self):
        """ Runs experiment. """
        
        self.create_trials()
        self.display_text('Waiting for scanner', keys=self.settings['mri'].get('sync', 't'))
        # ^ only real difference with simple_exp

        self.start_experiment()

        for trial in self.trials:
            trial.run()

        self.close()


if __name__ == '__main__':

    session = TestFMRISession(n_trials=10)
    session.run()