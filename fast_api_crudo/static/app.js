/* ═══════════════════════════════════════════════════════════════
   Fast API Crudo — React Admin UI
   ═══════════════════════════════════════════════════════════════ */

const { useState, useEffect, useCallback, useRef, Fragment } = React;
const CONFIG = window.CRUDO_CONFIG;
const IS_ADMIN = CONFIG.userRole === "admin";

/* ─── API helper ──────────────────────────────────────────── */

async function apiFetch(path, options = {}) {
    const url = `${CONFIG.apiBase}${path}`;
    const headers = { ...options.headers };
    if (options.body) headers["Content-Type"] = "application/json";

    const res = await fetch(url, { ...options, headers });

    // Redirect to login on 401
    if (res.status === 401) {
        window.location.href = CONFIG.prefix + "/login";
        return;
    }

    if (res.status === 204) return null;

    const data = await res.json().catch(() => null);
    if (!res.ok) {
        const detail = data?.detail;
        const msg =
            typeof detail === "string"
                ? detail
                : Array.isArray(detail)
                  ? detail.map((e) => e.msg || e.message || JSON.stringify(e)).join(", ")
                  : `Request failed (${res.status})`;
        throw new Error(msg);
    }
    return data;
}

/* ─── Toast ───────────────────────────────────────────────── */

function Toast({ message, type, onClose }) {
    useEffect(() => {
        const t = setTimeout(onClose, 4000);
        return () => clearTimeout(t);
    }, []);
    return (
        <div className={`toast toast--${type}`}>
            <span>{message}</span>
            <button className="toast__close" onClick={onClose}>
                &times;
            </button>
        </div>
    );
}

function ToastContainer({ toasts, onRemove }) {
    return (
        <div className="toast-container">
            {toasts.map((t) => (
                <Toast key={t.id} message={t.message} type={t.type} onClose={() => onRemove(t.id)} />
            ))}
        </div>
    );
}

/* ─── Modal ───────────────────────────────────────────────── */

function Modal({ show, title, onClose, wide, children }) {
    if (!show) return null;
    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className={`modal ${wide ? "modal--wide" : ""}`} onClick={(e) => e.stopPropagation()}>
                <div className="modal__header">
                    <h2>{title}</h2>
                    <button className="modal__close" onClick={onClose}>
                        &times;
                    </button>
                </div>
                <div className="modal__body">{children}</div>
            </div>
        </div>
    );
}

/* ─── Spinner ─────────────────────────────────────────────── */

function Spinner() {
    return <div className="spinner" />;
}

/* ─── Pagination ──────────────────────────────────────────── */

function Pagination({ page, pages, total, perPage, onChange, onPerPageChange }) {
    if (total === 0) return null;

    const start = (page - 1) * perPage + 1;
    const end = Math.min(page * perPage, total);

    const nums = [];
    let s = Math.max(1, page - 2);
    let e = Math.min(pages, page + 2);
    if (s > 1) {
        nums.push(1);
        if (s > 2) nums.push("…");
    }
    for (let i = s; i <= e; i++) nums.push(i);
    if (e < pages) {
        if (e < pages - 1) nums.push("…");
        nums.push(pages);
    }

    return (
        <div className="pagination">
            <div className="pagination__info">
                Showing <strong>{start}</strong>–<strong>{end}</strong> of <strong>{total}</strong>
            </div>
            <div className="pagination__controls">
                <button className="pagination__btn" disabled={page <= 1} onClick={() => onChange(page - 1)}>
                    ‹ Prev
                </button>
                {nums.map((n, i) =>
                    typeof n === "number" ? (
                        <button
                            key={i}
                            className={`pagination__btn ${n === page ? "pagination__btn--active" : ""}`}
                            onClick={() => onChange(n)}
                        >
                            {n}
                        </button>
                    ) : (
                        <span key={i} className="pagination__ellipsis">
                            …
                        </span>
                    ),
                )}
                <button className="pagination__btn" disabled={page >= pages} onClick={() => onChange(page + 1)}>
                    Next ›
                </button>
            </div>
            <div className="pagination__per-page">
                <select value={perPage} onChange={(ev) => onPerPageChange(Number(ev.target.value))}>
                    {[10, 25, 50, 100].map((n) => (
                        <option key={n} value={n}>
                            {n} / page
                        </option>
                    ))}
                </select>
            </div>
        </div>
    );
}

/* ─── Actions Dropdown ─────────────────────────────────────── */

function ActionsDropdown({ actions, selectedCount, onAction, userRole }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    const available = actions.filter((a) => a.role === "viewer" || userRole === "admin");
    if (!available.length) return null;

    return (
        <div className="actions-dropdown" ref={ref}>
            <button
                className="btn btn--secondary actions-dropdown__trigger"
                onClick={() => setOpen(!open)}
            >
                Actions {selectedCount > 0 && `(${selectedCount})`} ▾
            </button>
            {open && (
                <div className="actions-dropdown__menu">
                    {available.map((a) => (
                        <button
                            key={a.name}
                            className="actions-dropdown__item"
                            disabled={selectedCount === 0}
                            onClick={() => { setOpen(false); onAction(a); }}
                        >
                            {a.icon && <span className="actions-dropdown__icon">{a.icon}</span>}
                            {a.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

/* ─── Confirm Action Modal ────────────────────────────────── */

function ConfirmActionModal({ show, action, selectedCount, onConfirm, onCancel, running }) {
    if (!show || !action) return null;
    const message = action.confirm
        ? action.confirm.replace("{count}", String(selectedCount))
        : `Run "${action.label}" on ${selectedCount} record(s)?`;

    return (
        <Modal show={show} title={`${action.icon || ""} ${action.label}`.trim()} onClose={onCancel}>
            <div className="delete-confirm">
                <p>{message}</p>
                <div className="form-actions">
                    <button className="btn btn--secondary" onClick={onCancel} disabled={running}>Cancel</button>
                    <button className="btn btn--primary" onClick={onConfirm} disabled={running}>
                        {running ? "Running\u2026" : "Confirm"}
                    </button>
                </div>
            </div>
        </Modal>
    );
}

/* ─── Data Table ──────────────────────────────────────────── */

function DataTable({ columns, data, sortBy, sortDir, onSort, onEdit, onDelete, pkColumns, selectedPks, onToggleSelect, onToggleSelectAll, actions, onRowAction }) {
    const getPk = (rec) => pkColumns.map((pk) => rec[pk]).join("--");
    const hasActions = actions && actions.length > 0;

    const fmt = (value, col) => {
        if (value === null || value === undefined) return <span className="cell--null">NULL</span>;
        if (col.type === "boolean")
            return <span className={`cell--bool cell--bool-${value}`}>{value ? "✓ Yes" : "✗ No"}</span>;
        if (col.type === "datetime" || col.type === "date") {
            try {
                return new Date(value).toLocaleString();
            } catch {
                return String(value);
            }
        }
        if (col.type === "json" || col.type === "array") {
            const s = JSON.stringify(value);
            return <span title={s}>{s.length > 60 ? s.slice(0, 60) + "…" : s}</span>;
        }
        const s = String(value);
        if (s.length > 80) return <span title={s}>{s.slice(0, 80)}…</span>;
        return s;
    };

    if (!data.length) {
        return (
            <div className="empty-state">
                <div className="empty-state__icon">📭</div>
                <p>No records found</p>
            </div>
        );
    }

    return (
        <div className="table-container">
            <table className="data-table">
                <thead>
                    <tr>
                        {hasActions && (
                            <th className="data-table__th data-table__th--checkbox">
                                <input
                                    type="checkbox"
                                    checked={data.length > 0 && selectedPks.size === data.length}
                                    ref={(el) => { if (el) el.indeterminate = selectedPks.size > 0 && selectedPks.size < data.length; }}
                                    onChange={onToggleSelectAll}
                                />
                            </th>
                        )}
                        {columns.map((col) => (
                            <th
                                key={col.name}
                                className={`data-table__th ${sortBy === col.name ? "data-table__th--sorted" : ""}`}
                                onClick={() => onSort(col.name)}
                                title={`${col.sa_type}${col.nullable ? ", nullable" : ""}${col.primary_key ? ", PK" : ""}${col.is_foreign_key ? " → " + col.foreign_key_target : ""}`}
                            >
                                <span className="data-table__th-content">
                                    {col.primary_key && <span className="badge badge--pk">PK</span>}
                                    {col.is_foreign_key && <span className="badge badge--fk">FK</span>}
                                    {col.name}
                                    {sortBy === col.name && (
                                        <span className="sort-indicator">{sortDir === "asc" ? " ↑" : " ↓"}</span>
                                    )}
                                </span>
                            </th>
                        ))}
                        {IS_ADMIN && <th className="data-table__th data-table__th--actions">Actions</th>}
                    </tr>
                </thead>
                <tbody>
                    {data.map((rec, idx) => {
                        const pk = getPk(rec);
                        const isSelected = selectedPks.has(pk);
                        return (
                            <tr key={pk || idx} className={`data-table__tr ${isSelected ? "data-table__tr--selected" : ""}`}>
                                {hasActions && (
                                    <td className="data-table__td data-table__td--checkbox">
                                        <input
                                            type="checkbox"
                                            checked={isSelected}
                                            onChange={() => onToggleSelect(pk)}
                                        />
                                    </td>
                                )}
                                {columns.map((col) => (
                                    <td key={col.name} className="data-table__td">
                                        {fmt(rec[col.name], col)}
                                    </td>
                                ))}
                                {IS_ADMIN && (
                                    <td className="data-table__td data-table__td--actions">
                                        <button className="btn btn--sm btn--ghost" onClick={() => onEdit(rec)} title="Edit">✏️</button>
                                        <button className="btn btn--sm btn--ghost btn--danger" onClick={() => onDelete(rec)} title="Delete">🗑️</button>
                                        {hasActions && actions.map((a) => (
                                            <button
                                                key={a.name}
                                                className="btn btn--sm btn--ghost"
                                                onClick={() => onRowAction(a, rec)}
                                                title={a.label}
                                            >
                                                {a.icon || a.label.charAt(0)}
                                            </button>
                                        ))}
                                    </td>
                                )}
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

/* ─── Record Form ─────────────────────────────────────────── */

function RecordForm({ modelInfo, record, onSave, onCancel }) {
    const isEdit = record !== null;
    const allColumns = modelInfo.columns;

    const formColumns = allColumns.filter((col) => {
        if (isEdit) return true;
        return !col.is_auto_pk;
    });

    const [formData, setFormData] = useState(() => {
        if (isEdit) {
            const d = {};
            allColumns.forEach((col) => {
                let v = record[col.name];
                if ((col.type === "json" || col.type === "array") && v != null) {
                    v = JSON.stringify(v, null, 2);
                }
                d[col.name] = v != null ? v : "";
            });
            return d;
        }
        const d = {};
        formColumns.forEach((col) => {
            d[col.name] = col.type === "boolean" ? false : "";
        });
        return d;
    });

    const [errors, setErrors] = useState({});
    const [saving, setSaving] = useState(false);

    const handleChange = (name, value) => {
        setFormData((prev) => ({ ...prev, [name]: value }));
        setErrors((prev) => ({ ...prev, [name]: null }));
    };

    const handleSubmit = async (ev) => {
        ev.preventDefault();

        const newErrors = {};
        formColumns.forEach((col) => {
            if (!col.nullable && !col.has_default && !col.primary_key) {
                const v = formData[col.name];
                if (v === "" || v === null || v === undefined) {
                    newErrors[col.name] = "Required";
                }
            }
        });
        if (Object.keys(newErrors).length) {
            setErrors(newErrors);
            return;
        }

        const payload = {};
        const cols = isEdit ? allColumns : formColumns;
        cols.forEach((col) => {
            if (isEdit && col.primary_key) return;
            let v = formData[col.name];

            if (v === "" && col.nullable) {
                payload[col.name] = null;
                return;
            }
            if (v === "" && col.has_default && !isEdit) return;

            if (col.type === "integer") {
                payload[col.name] = v === "" ? null : parseInt(v, 10);
            } else if (col.type === "number") {
                payload[col.name] = v === "" ? null : parseFloat(v);
            } else if (col.type === "boolean") {
                payload[col.name] = Boolean(v);
            } else if (col.type === "json" || col.type === "array") {
                try {
                    payload[col.name] = typeof v === "string" ? JSON.parse(v) : v;
                } catch {
                    payload[col.name] = v;
                }
            } else {
                payload[col.name] = v;
            }
        });

        setSaving(true);
        try {
            await onSave(payload);
        } catch {
            setSaving(false);
        }
    };

    const renderInput = (col) => {
        const v = formData[col.name] ?? "";
        const disabled = isEdit && col.primary_key;

        if (col.type === "boolean") {
            return (
                <label className="checkbox-label">
                    <input
                        type="checkbox"
                        checked={Boolean(v)}
                        onChange={(ev) => handleChange(col.name, ev.target.checked)}
                        disabled={disabled}
                    />
                    <span>{v ? "Yes" : "No"}</span>
                </label>
            );
        }
        if (col.enum_values && col.enum_values.length) {
            return (
                <select
                    className="form-select"
                    value={v}
                    onChange={(ev) => handleChange(col.name, ev.target.value)}
                    disabled={disabled}
                >
                    <option value="">— Select —</option>
                    {col.enum_values.map((opt) => (
                        <option key={opt} value={opt}>
                            {opt}
                        </option>
                    ))}
                </select>
            );
        }
        if (col.type === "json" || col.type === "array") {
            return (
                <textarea
                    className="form-textarea form-textarea--code"
                    value={typeof v === "object" ? JSON.stringify(v, null, 2) : v}
                    onChange={(ev) => handleChange(col.name, ev.target.value)}
                    rows={4}
                    disabled={disabled}
                />
            );
        }
        if (col.type === "datetime") {
            let dv = v;
            if (typeof dv === "string" && dv.length > 16) dv = dv.slice(0, 16);
            return (
                <input
                    type="datetime-local"
                    className="form-input"
                    value={dv}
                    onChange={(ev) => handleChange(col.name, ev.target.value)}
                    disabled={disabled}
                />
            );
        }
        if (col.type === "date") {
            return (
                <input
                    type="date"
                    className="form-input"
                    value={v}
                    onChange={(ev) => handleChange(col.name, ev.target.value)}
                    disabled={disabled}
                />
            );
        }
        if (col.type === "integer" || col.type === "number") {
            return (
                <input
                    type="number"
                    className="form-input"
                    value={v}
                    onChange={(ev) => handleChange(col.name, ev.target.value)}
                    disabled={disabled}
                    step={col.type === "number" ? "any" : "1"}
                />
            );
        }
        if (col.max_length && col.max_length > 255) {
            return (
                <textarea
                    className="form-textarea"
                    value={v}
                    onChange={(ev) => handleChange(col.name, ev.target.value)}
                    rows={3}
                    disabled={disabled}
                    maxLength={col.max_length}
                />
            );
        }
        return (
            <input
                type="text"
                className="form-input"
                value={v}
                onChange={(ev) => handleChange(col.name, ev.target.value)}
                disabled={disabled}
                maxLength={col.max_length || undefined}
            />
        );
    };

    return (
        <form onSubmit={handleSubmit} className="record-form">
            <div className="form-grid">
                {formColumns.map((col) => (
                    <div key={col.name} className={`form-group ${errors[col.name] ? "form-group--error" : ""}`}>
                        <label className="form-label">
                            {col.name}
                            {!col.nullable && !col.has_default && !col.primary_key && (
                                <span className="form-required">*</span>
                            )}
                            <span className="form-type-hint">{col.sa_type}</span>
                        </label>
                        {renderInput(col)}
                        {errors[col.name] && <span className="form-error">{errors[col.name]}</span>}
                        {col.comment && <span className="form-hint">{col.comment}</span>}
                    </div>
                ))}
            </div>
            <div className="form-actions">
                <button type="button" className="btn btn--secondary" onClick={onCancel} disabled={saving}>
                    Cancel
                </button>
                <button type="submit" className="btn btn--primary" disabled={saving}>
                    {saving ? "Saving…" : isEdit ? "Update Record" : "Create Record"}
                </button>
            </div>
        </form>
    );
}

/* ─── Sidebar ─────────────────────────────────────────────── */

function Sidebar({ models, selected, onSelect }) {
    const [filter, setFilter] = useState("");

    const filtered = filter
        ? models.filter(
              (m) =>
                  m.model_name.toLowerCase().includes(filter.toLowerCase()) ||
                  m.name.toLowerCase().includes(filter.toLowerCase()),
          )
        : models;

    return (
        <aside className="sidebar">
            <div className="sidebar__header">
                <span className="sidebar__logo">🍖</span>
                <h1 className="sidebar__title">{CONFIG.title}</h1>
            </div>
            {models.length > 8 && (
                <div style={{ padding: "0 8px 4px" }}>
                    <input
                        type="text"
                        className="search-box__input"
                        style={{ width: "100%" }}
                        placeholder="Filter models…"
                        value={filter}
                        onChange={(ev) => setFilter(ev.target.value)}
                    />
                </div>
            )}
            <nav className="sidebar__nav">
                {filtered.map((m) => (
                    <button
                        key={m.name}
                        className={`sidebar__item ${selected === m.name ? "sidebar__item--active" : ""}`}
                        onClick={() => onSelect(m.name)}
                    >
                        <span className="sidebar__item-name">{m.model_name}</span>
                        <span className="sidebar__item-count">{m.count >= 0 ? m.count : "?"}</span>
                    </button>
                ))}
                {filtered.length === 0 && (
                    <div style={{ padding: "12px", color: "rgba(255,255,255,.4)", fontSize: "12px" }}>
                        No models match
                    </div>
                )}
            </nav>
            <div className="sidebar__footer">
                <div className="sidebar__user">
                    <span className="sidebar__user-name" title={CONFIG.userEmail}>
                        {CONFIG.userName || CONFIG.userEmail}
                    </span>
                    <span className="sidebar__user-role">{CONFIG.userRole}</span>
                    <a href={CONFIG.logoutUrl} className="sidebar__logout" title="Logout">Logout</a>
                </div>
                <span className="sidebar__version">Crudo v{CONFIG.version || "0.2.0"}</span>
            </div>
        </aside>
    );
}

/* ─── App ─────────────────────────────────────────────────── */

function App() {
    const [models, setModels] = useState([]);
    const [selectedModel, setSelectedModel] = useState(null);
    const [loading, setLoading] = useState(true);
    const [dataLoading, setDataLoading] = useState(false);
    const [data, setData] = useState({ items: [], total: 0, page: 1, per_page: 25, pages: 0 });
    const [page, setPage] = useState(1);
    const [perPage, setPerPage] = useState(25);
    const [sortBy, setSortBy] = useState(null);
    const [sortDir, setSortDir] = useState("asc");
    const [search, setSearch] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const [showForm, setShowForm] = useState(false);
    const [editingRecord, setEditingRecord] = useState(null);
    const [showDelete, setShowDelete] = useState(false);
    const [deletingRecord, setDeletingRecord] = useState(null);
    const [selectedPks, setSelectedPks] = useState(new Set());
    const [actionModal, setActionModal] = useState(null);
    const [actionRunning, setActionRunning] = useState(false);
    const [toasts, setToasts] = useState([]);

    const addToast = (message, type = "success") =>
        setToasts((p) => [...p, { id: Date.now() + Math.random(), message, type }]);
    const removeToast = (id) => setToasts((p) => p.filter((t) => t.id !== id));

    /* load models */
    useEffect(() => {
        apiFetch("/_meta/models")
            .then((result) => {
                if (!result) return; // redirected to login
                setModels(result);
                if (result.length) setSelectedModel(result[0].name);
                setLoading(false);
            })
            .catch((err) => {
                addToast("Failed to load models: " + err.message, "error");
                setLoading(false);
            });
    }, []);

    /* debounce search */
    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedSearch(search);
            setPage(1);
        }, 300);
        return () => clearTimeout(timer);
    }, [search]);

    /* fetch records */
    const fetchData = useCallback(() => {
        if (!selectedModel) return;
        setDataLoading(true);
        const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
        if (sortBy) params.set("sort_by", sortBy);
        if (sortDir) params.set("sort_dir", sortDir);
        if (debouncedSearch) params.set("search", debouncedSearch);

        apiFetch(`/${selectedModel}?${params}`)
            .then((result) => {
                if (!result) return; // redirected to login
                setData(result);
                setDataLoading(false);
            })
            .catch((err) => {
                addToast("Failed to load records: " + err.message, "error");
                setDataLoading(false);
            });
    }, [selectedModel, page, perPage, sortBy, sortDir, debouncedSearch]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    /* handlers */
    const handleSelectModel = (name) => {
        if (name === selectedModel) return;
        setSelectedModel(name);
        setSelectedPks(new Set());
        setPage(1);
        setSortBy(null);
        setSortDir("asc");
        setSearch("");
        setDebouncedSearch("");
    };

    const handleSort = (col) => {
        if (sortBy === col) {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortBy(col);
            setSortDir("asc");
        }
    };

    const handlePageChange = (p) => setPage(p);
    const handlePerPageChange = (pp) => {
        setPerPage(pp);
        setPage(1);
    };

    const getModelInfo = () => models.find((m) => m.name === selectedModel);

    const getPkValue = (rec) => {
        const info = getModelInfo();
        return info ? info.pk_columns.map((pk) => rec[pk]).join("--") : "";
    };

    const refreshModels = () => apiFetch("/_meta/models").then((r) => { if (r) setModels(r); }).catch(() => {});

    const handleCreate = () => {
        setEditingRecord(null);
        setShowForm(true);
    };

    const handleEdit = (rec) => {
        setEditingRecord(rec);
        setShowForm(true);
    };

    const handleSave = async (payload) => {
        if (editingRecord) {
            await apiFetch(`/${selectedModel}/${getPkValue(editingRecord)}`, {
                method: "PUT",
                body: JSON.stringify(payload),
            });
            addToast("Record updated successfully");
        } else {
            await apiFetch(`/${selectedModel}`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            addToast("Record created successfully");
        }
        setShowForm(false);
        setEditingRecord(null);
        fetchData();
        refreshModels();
    };

    const handleDeleteClick = (rec) => {
        setDeletingRecord(rec);
        setShowDelete(true);
    };

    const handleDeleteConfirm = async () => {
        try {
            await apiFetch(`/${selectedModel}/${getPkValue(deletingRecord)}`, { method: "DELETE" });
            addToast("Record deleted successfully");
            setShowDelete(false);
            setDeletingRecord(null);
            fetchData();
            refreshModels();
        } catch (err) {
            addToast(err.message, "error");
        }
    };

    /* selection + actions */
    const handleToggleSelect = (pk) => {
        setSelectedPks((prev) => {
            const next = new Set(prev);
            if (next.has(pk)) next.delete(pk); else next.add(pk);
            return next;
        });
    };

    const handleToggleSelectAll = () => {
        if (selectedPks.size === data.items.length) {
            setSelectedPks(new Set());
        } else {
            setSelectedPks(new Set(data.items.map((r) => getPkValue(r))));
        }
    };

    const executeAction = async (action, pks) => {
        setActionRunning(true);
        try {
            const result = await apiFetch(`/${selectedModel}/_action/${action.name}`, {
                method: "POST",
                body: JSON.stringify({ pks }),
            });
            if (result) addToast(result.message || "Action completed", "success");
            setSelectedPks(new Set());
            fetchData();
            refreshModels();
        } catch (err) {
            addToast(err.message, "error");
        } finally {
            setActionRunning(false);
            setActionModal(null);
        }
    };

    const handleBulkAction = (action) => {
        setActionModal({ action, pks: [...selectedPks] });
    };

    const handleRowAction = (action, record) => {
        setActionModal({ action, pks: [getPkValue(record)] });
    };

    /* loading */
    if (loading) {
        return (
            <div className="loading-screen">
                <div className="loading-screen__content">
                    <span className="loading-screen__logo">🍖</span>
                    <Spinner />
                    <p>Loading models…</p>
                </div>
            </div>
        );
    }

    const modelInfo = getModelInfo();
    const currentActions = modelInfo?.actions || [];

    return (
        <div className="app">
            <Sidebar models={models} selected={selectedModel} onSelect={handleSelectModel} />

            <main className="content">
                {modelInfo ? (
                    <Fragment>
                        <div className="content__header">
                            <div className="content__header-left">
                                <h2 className="content__title">{modelInfo.model_name}</h2>
                                <span className="content__subtitle">
                                    {modelInfo.name} · {data.total} record{data.total !== 1 ? "s" : ""}
                                </span>
                            </div>
                            <div className="content__header-right">
                                {currentActions.length > 0 && (
                                    <ActionsDropdown
                                        actions={currentActions}
                                        selectedCount={selectedPks.size}
                                        onAction={handleBulkAction}
                                        userRole={CONFIG.userRole}
                                    />
                                )}
                                <div className="search-box">
                                    <input
                                        type="text"
                                        className="search-box__input"
                                        placeholder="Search…"
                                        value={search}
                                        onChange={(ev) => setSearch(ev.target.value)}
                                    />
                                    {search && (
                                        <button className="search-box__clear" onClick={() => setSearch("")}>
                                            &times;
                                        </button>
                                    )}
                                </div>
                                {IS_ADMIN && (
                                    <button className="btn btn--primary" onClick={handleCreate}>
                                        + New Record
                                    </button>
                                )}
                            </div>
                        </div>

                        <div className="content__body">
                            {dataLoading && (
                                <div className="content__loading">
                                    <Spinner />
                                </div>
                            )}
                            <DataTable
                                columns={modelInfo.columns}
                                data={data.items}
                                sortBy={sortBy}
                                sortDir={sortDir}
                                onSort={handleSort}
                                onEdit={handleEdit}
                                onDelete={handleDeleteClick}
                                pkColumns={modelInfo.pk_columns}
                                selectedPks={selectedPks}
                                onToggleSelect={handleToggleSelect}
                                onToggleSelectAll={handleToggleSelectAll}
                                actions={currentActions}
                                onRowAction={handleRowAction}
                            />
                        </div>

                        <Pagination
                            page={page}
                            pages={data.pages}
                            total={data.total}
                            perPage={perPage}
                            onChange={handlePageChange}
                            onPerPageChange={handlePerPageChange}
                        />
                    </Fragment>
                ) : (
                    <div className="empty-state">
                        <div className="empty-state__icon">🍖</div>
                        <h2>Welcome to Crudo</h2>
                        <p>Select a model from the sidebar to get started.</p>
                    </div>
                )}
            </main>

            {/* Create / Edit modal (admin only) */}
            {IS_ADMIN && (
                <Modal
                    show={showForm}
                    title={editingRecord ? `Edit ${modelInfo?.model_name}` : `New ${modelInfo?.model_name}`}
                    onClose={() => {
                        setShowForm(false);
                        setEditingRecord(null);
                    }}
                    wide
                >
                    {modelInfo && (
                        <RecordForm
                            modelInfo={modelInfo}
                            record={editingRecord}
                            onSave={handleSave}
                            onCancel={() => {
                                setShowForm(false);
                                setEditingRecord(null);
                            }}
                        />
                    )}
                </Modal>
            )}

            {/* Delete confirmation (admin only) */}
            {IS_ADMIN && (
                <Modal
                    show={showDelete}
                    title="Confirm Deletion"
                    onClose={() => {
                        setShowDelete(false);
                        setDeletingRecord(null);
                    }}
                >
                    <div className="delete-confirm">
                        <p>Are you sure you want to delete this record? This action cannot be undone.</p>
                        {deletingRecord && modelInfo && (
                            <div className="delete-confirm__preview">
                                {modelInfo.pk_columns.map((pk) => (
                                    <span key={pk} className="delete-confirm__pk">
                                        {pk}: <strong>{String(deletingRecord[pk])}</strong>
                                    </span>
                                ))}
                            </div>
                        )}
                        <div className="form-actions">
                            <button
                                className="btn btn--secondary"
                                onClick={() => {
                                    setShowDelete(false);
                                    setDeletingRecord(null);
                                }}
                            >
                                Cancel
                            </button>
                            <button className="btn btn--danger" onClick={handleDeleteConfirm}>
                                Delete Record
                            </button>
                        </div>
                    </div>
                </Modal>
            )}

            {/* Action confirmation */}
            <ConfirmActionModal
                show={!!actionModal}
                action={actionModal?.action}
                selectedCount={actionModal?.pks?.length || 0}
                onConfirm={() => executeAction(actionModal.action, actionModal.pks)}
                onCancel={() => setActionModal(null)}
                running={actionRunning}
            />

            <ToastContainer toasts={toasts} onRemove={removeToast} />
        </div>
    );
}

/* ─── Mount ───────────────────────────────────────────────── */

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
