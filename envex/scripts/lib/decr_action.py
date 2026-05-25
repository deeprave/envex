import argparse

__all__ = ("Decrement",)


# noinspection PyShadowingBuiltins
class Decrement(argparse.Action):
    def __init__(
        self,
        option_strings,
        dest: str,
        default: int | None = None,
        required: bool = False,
        help: str | None = None,
    ):
        super().__init__(
            option_strings, dest, nargs=0, default=default, required=required, help=help
        )

    # noinspection PyShadowingNames
    def __call__(self, parser, namespace, values, option_string=None):
        current_value = getattr(namespace, self.dest, self.default or 0)
        try:
            setattr(namespace, self.dest, current_value - 1)
        except TypeError:
            pass
