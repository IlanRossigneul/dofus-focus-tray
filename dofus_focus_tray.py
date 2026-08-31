import sys

from app.application import Application

if __name__ == "__main__":
    sys.exit(Application().run(sys.argv[1:]))
