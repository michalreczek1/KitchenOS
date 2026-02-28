from db import Base, engine
import models  # noqa: F401


def main() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    main()
