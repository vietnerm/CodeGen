-- SQL của core SDK (viết tay, theo dialect chuẩn PostgreSQL).
-- Generator lint + chuyển sang mọi dialect cùng với SQL sinh ra. Mọi core (Java/C++/…) dùng chung.

-- name: core.login
SELECT u.user_id, u.user_name, u.status, c.password_hash
FROM zz.app_user u
JOIN zz.app_credential c ON c.user_id = u.user_id
WHERE u.user_id = :user_id;

-- name: core.user_units
SELECT tenant_id, unit_code, is_primary
FROM zz.user_unit
WHERE user_id = :user_id AND status = 'A'
ORDER BY tenant_id, is_primary DESC, unit_code;

-- name: core.permission
SELECT rf.right_mask
FROM zz.user_role ur
JOIN zz.role r ON r.role_id = ur.role_id
JOIN zz.role_function rf ON rf.role_id = ur.role_id
JOIN zz.app_user u ON u.user_id = ur.user_id
WHERE ur.tenant_id = :_tenant AND ur.user_id = :_user AND rf.function_id = :function_id
  AND ur.approval_status = 'A' AND r.status = 'A' AND u.status = 'A'
  AND (ur.effective_from IS NULL OR ur.effective_from <= CURRENT_DATE)
  AND (ur.effective_to IS NULL OR ur.effective_to >= CURRENT_DATE);

-- name: core.user_masks
SELECT rf.function_id, rf.right_mask
FROM zz.user_role ur
JOIN zz.role r ON r.role_id = ur.role_id
JOIN zz.role_function rf ON rf.role_id = ur.role_id
JOIN zz.app_user u ON u.user_id = ur.user_id
WHERE ur.tenant_id = :_tenant AND ur.user_id = :_user
  AND ur.approval_status = 'A' AND r.status = 'A' AND u.status = 'A'
  AND (ur.effective_from IS NULL OR ur.effective_from <= CURRENT_DATE)
  AND (ur.effective_to IS NULL OR ur.effective_to >= CURRENT_DATE);

-- name: core.functions
SELECT f.function_id, f.function_name, f.function_type, f.url, f.sort_order, t.parent_function_id
FROM zz.function f
LEFT JOIN zz.function_tree t ON t.function_id = f.function_id
ORDER BY f.sort_order, f.function_id;

-- name: core.codemap_exists
SELECT COUNT(*) AS cnt
FROM zz.codemap c
WHERE c.group_code = :group_code AND c.code = :code AND c.status = 'A'
  AND (c.tenant_id = :_tenant
       OR (c.tenant_id = '*' AND NOT EXISTS (
             SELECT 1 FROM zz.codemap t
             WHERE t.tenant_id = :_tenant AND t.group_code = c.group_code AND t.code = c.code)))
  AND (c.effective_from IS NULL OR c.effective_from <= CURRENT_DATE)
  AND (c.effective_to IS NULL OR c.effective_to >= CURRENT_DATE);

-- name: core.codemap_list
SELECT c.code, c.parent_code, c.seq, c.attrs, c.is_system,
       COALESCE(lt.label, lg.label, c.code) AS label
FROM zz.codemap c
LEFT JOIN zz.codemap_label lt
       ON lt.tenant_id = :_tenant AND lt.group_code = c.group_code AND lt.code = c.code AND lt.lang = :lang
LEFT JOIN zz.codemap_label lg
       ON lg.tenant_id = '*' AND lg.group_code = c.group_code AND lg.code = c.code AND lg.lang = :lang
WHERE c.group_code = :group_code AND c.status = 'A'
  AND (c.tenant_id = :_tenant
       OR (c.tenant_id = '*' AND NOT EXISTS (
             SELECT 1 FROM zz.codemap t
             WHERE t.tenant_id = :_tenant AND t.group_code = c.group_code AND t.code = c.code)))
  AND (c.effective_from IS NULL OR c.effective_from <= CURRENT_DATE)
  AND (c.effective_to IS NULL OR c.effective_to >= CURRENT_DATE)
ORDER BY c.seq, c.code;

-- name: core.codemap_group
SELECT group_code, group_name, parent_group, tenant_editable, data_version, status
FROM zz.codemap_group
WHERE group_code = :group_code;

-- name: core.audit_insert
INSERT INTO zz.audit_log (tenant_id, actor_id, function_id, action, target, detail)
VALUES (:_tenant, :_user, :function_id, :action, :target, :detail);
