from exptools2.session import Session
from exptools2.trial import Trial
from simple_exp import TestTrial, TestSession


class TestFMRISession(TestSession):
    """ Simple session with x trials. """

    def run(self):
        """ Runs experiment. """
        
        self.display_text('Waiting for scanner', keys=self.settings['mri'].get('sync', 't'))
        # ^ only real difference with simple_exp

        self.start_experiment()

        for trial in self.trials:
            trial.run()

        self.close()


if __name__ == '__main__':

    session = TestFMRISession('sub-01', n_trials=10)
    session.create_trials(durations=(15, 15), timing='frames')
    session.run()