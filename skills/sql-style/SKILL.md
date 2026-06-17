---
name: sql-style
description: SQL style guide and best practices for writing clean, maintainable queries
---

# SQL Style Guide

## Naming Conventions
- Use `snake_case` for table and column names
- Prefix boolean columns with `is_`, `has_`, or `should_`
- Use plural nouns for table names: `users`, `orders`, `products`

## Formatting
- One column per line in SELECT clauses
- Indent subqueries with 2 spaces
- Use UPPERCASE for SQL keywords, lowercase for identifiers

## Best Practices
- Always use explicit JOIN syntax (not implicit comma joins)
- Add comments for complex WHERE clauses
- Use CTEs (`WITH`) instead of nested subqueries for readability

## Example
```sql
SELECT
    u.id,
    u.email,
    COUNT(o.id) AS order_count
FROM users AS u
LEFT JOIN orders AS o
    ON u.id = o.user_id
    AND o.status = 'active'
WHERE u.is_deleted = false
GROUP BY u.id, u.email
ORDER BY order_count DESC
LIMIT 10;
```
