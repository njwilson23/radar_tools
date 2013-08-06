
#import filters

#def get_commands(module):
#    """ Return the commands in module """
#    commands = {}
#    for key in module.__dict__:
#        val = module.__dict__[key]
#        if (type(val) is type) and val.__base__ is filters.FilterCommand:
#            commands[val.cmd] = val
#    return commands

import traceback

def apply_command(registry, inputs, app):
    """ Attempt to find a Command matching an input_string, and apply. Raises
    KeyError otherwise. """
    if len(inputs) > 1:
        cmd = inputs[0]
        args = inputs[1:]
    else:
        cmd = inputs[0]
        args = []

    if cmd in registry:

        cmdclass = registry[cmd]()
        if cmdclass._type == "Filter":
            stateobj = app.line
        else:
            stateobj = app

        print args

        try:
            cmdclass.apply(stateobj, args)
        except Exception as e:
            traceback.print_exc()
            print CommandApplicationError(e)

    else:
         raise KeyError("No command definition '{0}' found".format(cmd))


def help_command(registry, cmd):
    """ Print the help documentation for *cmd*, or raise Key if it cannot be
    found. """
    if cmd in registry:
        return registry[cmd].helpstr
    else:
         raise KeyError("No command definition '{0}' found".format(cmd))

def list_filters():
    return sorted(get_commands(filters).keys())

class CommandApplicationError(Exception):
    def __init__(self, exception):
        self.e = exception
    def __str__(self):
        return self.e.__str__()

