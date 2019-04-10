import click
import os.path as op
from .session import FLocSession


@click.command()
@click.option('--sub', default='01', type=str, help='Subject nr (e.g., 01)')
@click.option('--run', default=1, type=int, help='Run nr')
@click.option('--dummies', default=None, type=int, help='Number of dummy scans')
@click.option('--scrambled', is_flag=True, help='Whether to include scrambled category')
@click.option('--settings', default=None, type=str, help='Settings file')
@click.option('--stimdir', default=None, type=str, help='fLoc stimulus directory')
@click.option('--ntrials', default=None, type=int, help='number of trials (for debugging)')
def main_api(sub, run, dummies, scrambled, settings, stimdir, ntrials):

    if stimdir is None:
        stimdir = op.abspath('fLoc')

    fLoc_session = FLocSession(
        sub=sub, 
        run=run,
        output_str=f'sub-{sub}_task-localizer_run-{run}',
        settings_file=settings,
        stim_dir=stimdir,
        scrambled=scrambled,
        dummies=dummies,
        ntrials=ntrials
    )

    fLoc_session.run()
    fLoc_session.quit()
