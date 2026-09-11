import asyncio

from database import init_db, close_db, pool, queries


def show_menu():
    print("\n=== Меню ===")
    print("1 - Показать всех пользователей")
    print("2 - Создать пользователя")
    print("3 - Удалить пользователя")
    print("0 - Выход")


async def list_users(conn):
    found = False

    print("\n=== Пользователи ===")

    async for user in queries.list_users(conn):
        found = True

        print(
            f"id={user[0]} | "
            f"name={user[1]} | "
            f"email={user[2]}"
        )

    if not found:
        print("Пользователей нет.")


async def create_user(conn):
    name = input("Имя: ").strip()
    email = input("Email: ").strip()

    if not name or not email:
        print("Имя и email не могут быть пустыми.")
        return

    async with conn.transaction():
        user = await queries.create_user(
            conn,
            name=name,
            email=email,
        )

    print(f"Создан пользователь: {user}")


async def delete_user(conn):
    user_id = input("ID пользователя для удаления: ").strip()

    if not user_id.isdigit():
        print("ID должен быть числом.")
        return

    async with conn.transaction():
        await queries.delete_user(
            conn,
            user_id=int(user_id),
        )

    print("Пользователь удалён.")


async def main():
    await init_db()

    try:
        async with pool.connection() as conn:
            while True:
                show_menu()

                choice = input("Выбор: ").strip()

                if choice == "1":
                    await list_users(conn)

                elif choice == "2":
                    await create_user(conn)

                elif choice == "3":
                    await delete_user(conn)

                elif choice == "0":
                    print("Выход.")
                    break

                else:
                    print("Неверный выбор.")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)