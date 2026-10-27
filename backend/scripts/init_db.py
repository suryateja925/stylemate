from backend.app.database import init_db


if __name__ == "__main__":
    init_db()
    print("StyleMate SQLite schema is ready.")
