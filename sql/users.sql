-- name: get_user_by_id^
SELECT id, name, email
FROM users
WHERE id = %(user_id)s;

-- name: list_users
SELECT id, name, email
FROM users
ORDER BY id;

-- name: create_user^
INSERT INTO users (name, email)
VALUES (%(name)s, %(email)s)
RETURNING id, name, email;

-- name: delete_user!
DELETE FROM users
WHERE id = %(user_id)s;