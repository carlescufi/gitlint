# This code is mostly duplicated from the `gitlint.shell` module. We consciously duplicate this code as to not depend
# on gitlint internals for our integration testing framework.

import subprocess

from qa.utils import DEFAULT_ENCODING, USE_SH_LIB

if USE_SH_LIB:
    from sh import (
        echo,
        git,
        gitlint,
    )

    gitlint = gitlint.bake(_unify_ttys=True, _tty_in=True)

    # import exceptions separately, this makes it a little easier to mock them out in the unit tests
    from sh import (
        CommandNotFound,
        ErrorReturnCode,
        RunningCommand,
    )
else:

    class CommandNotFound(Exception):
        """Exception indicating a command was not found during execution"""

    class RunningCommand:
        ...

    class ShResult(RunningCommand):
        """Result wrapper class. We use this to more easily migrate from using https://amoffat.github.io/sh/ to using
        the builtin subprocess module."""

        def __init__(self, full_cmd, stdout, stderr="", exitcode=0):
            self.full_cmd = full_cmd
            # TODO(jorisroovers): The 'sh' library by default will merge stdout and stderr. We mimic this behavior
            # for now until we fully remove the 'sh' library.
            self._stdout = stdout + stderr
            self._stderr = stderr
            self.exit_code = exitcode

        def __str__(self):
            return self.stdout.decode(DEFAULT_ENCODING)

        def __unicode__(self):
            return self.stdout

        @property
        def stdout(self):
            return self._stdout

        @property
        def stderr(self):
            return self._stderr

        def __getattr__(self, p):
            # https://github.com/amoffat/sh/blob/e0ed8e244e9d973ef4e0749b2b3c2695e7b5255b/sh.py#L952=
            _unicode_methods = set(dir(str()))  # noqa
            if p in _unicode_methods:
                return getattr(str(self), p)

            raise AttributeError

    class ErrorReturnCode(ShResult, Exception):
        """ShResult subclass for unexpected results (acts as an exception)."""

    def git(*command_parts, **kwargs):
        return run_command("git", *command_parts, **kwargs)

    def echo(*command_parts, **kwargs):
        return run_command("echo", *command_parts, **kwargs)

    def gitlint(*command_parts, **kwargs):
        return run_command("gitlint", *command_parts, **kwargs)

    def run_command(command, *args, **kwargs):
        args = [command] + list(args)
        return _exec(*args, **kwargs)

    def _exec(*args, **kwargs):
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.PIPE,
            "shell": kwargs.get("_tty_out", False),
            "cwd": kwargs.get("_cwd", None),
            "env": kwargs.get("_env", None),
        }

        stdin_input = None
        if len(args) > 1 and isinstance(args[1], ShResult):
            stdin_input = args[1].stdout
            # pop args[1] from the array and use it as stdin
            args = list(args)
            args.pop(1)
            popen_kwargs["stdin"] = subprocess.PIPE

        try:
            with subprocess.Popen(args, **popen_kwargs) as p:
                result = p.communicate(stdin_input)

        except FileNotFoundError as exc:
            raise CommandNotFound from exc

        exit_code = p.returncode
        stdout = result[0]
        stderr = result[1]  # 'sh' does not decode the stderr bytes to unicode
        full_cmd = "" if args is None else " ".join(args)

        # If not _ok_code is specified, then only a 0 exit code is allowed
        ok_exit_codes = kwargs.get("_ok_code", [0])

        if exit_code in ok_exit_codes:
            return ShResult(full_cmd, stdout, stderr, exit_code)

        # Unexpected error code => raise ErrorReturnCode
        raise ErrorReturnCode(full_cmd, stdout, stderr, p.returncode)
