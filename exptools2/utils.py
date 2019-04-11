import pickle


def save_experiment(session, output_str, engine='pickle'):
    """ Saves Session object.

    parameters
    ----------
    session : Session instance
        Object created with Session class
    output_str : str
        name of output file (saves to current cwd) or complete filepath
    engine : str (default = 'pickle')
        Select engine to save object, either 'pickle' or 'joblib'
    """

    if engine == 'pickle':
        with open(output_str + '.pkl', 'w') as f_out:
            pickle.dump(session, f_out)
    else:
        raise ValueError("Engine not recognized, use 'pickle'")
