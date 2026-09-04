from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self) -> None:
        self.engine = None
        self.session = scoped_session(sessionmaker(expire_on_commit=False))

    def init_app(self, app) -> None:
        self.engine = create_engine(app.config["DATABASE_URL"])
        self.session.configure(bind=self.engine)
        app.extensions["clusterweaver_db"] = self
        app.teardown_appcontext(lambda _error=None: self.session.remove())


db = Database()

