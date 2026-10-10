"""python3 -m bloodless: the window without arguments, the command line with them."""
import sys


def main():
    if len(sys.argv) > 1:
        from .cli import main as run
    else:
        from .gui import main as run
    return run()


if __name__ == "__main__":
    sys.exit(main())
