"""
created on 06/03/2019
Author: Sjoerd Evelo
--------------------
functions:
----------
save_experiment
    Saves Session object using specified engine
"""
import dill
import joblib


def save_experiment(session, path, engine='pickle'):
    """ Saves Session object.

    parameters
    ----------
    session : Session instance
        Object created with Session class
    path : str
        name of output file (saves to current wcd) or complete filepath
    engine : str (default = 'pickle')
        Select engine to save object, either 'pickle' or 'joblib'
    """
    if engine == 'pickle':
        dill.dump(session, open(path, 'wb'))
    elif engine == 'joblib':
        joblib.dump(session, path)
    else:
        raise ValueError("Engine not recognized, use 'pickle' or 'joblib'")
