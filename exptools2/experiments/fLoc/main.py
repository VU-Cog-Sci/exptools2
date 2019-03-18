import click
import os.path as op
from .session import FLocSession


@click.command()
@click.option('--sub', default='01', type=str, help='Subject nr (e.g., 01)')
@click.option('--run', default=1, type=int, help='Run nr')
@click.option('--settings', default=None, type=str, help='Settings file')
@click.option('--stimdir', default=None, type=str, help='fLoc stimulus directory')
def main_api(sub, run, settings, stimdir):

    if stimdir is None:
        stimdir = op.abspath('fLoc')

    fLoc_session = FLocSession(
        sub=sub, 
        run=run,
        output_str=f'sub-{sub}_task-localizer_run-{run}',
        settings_file=settings,
        stim_dir=stimdir,
    )

    fLoc_session.run()
