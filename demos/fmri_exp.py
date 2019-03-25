from simple_exp import TestTrial, TestSession


class TestFMRISession(TestSession):
    """ Simple session with x trials. """

    def run(self):
        """ Runs experiment. """
        
        self.display_text('Waiting for scanner', keys=self.settings['mri'].get('sync', 't'))
        # ^ only real difference with simple_exp

        self.start_experiment(wait_n_triggers=4)

        for trial in self.trials:
            trial.run()

        self.close()


if __name__ == '__main__':

    session = TestFMRISession('sub-01', n_trials=10)
    session.create_trials(durations=(0.5, .5), timing='seconds')
    session.run()
