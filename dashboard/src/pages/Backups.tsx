import { useState } from "react";
import { format } from "date-fns";
import { createBackup, restoreBackup, type Snapshot } from "../api/client";
import { useBackups } from "../hooks/useBackups";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function snapshotLabel(s: Snapshot): string {
  // Keys look like "<prefix>/<kind>/<timestamp>.dump.gz" — pull the timestamp.
  const filename = s.key.split("/").pop() ?? s.key;
  return filename.replace(".dump.gz", "");
}

export default function Backups() {
  const { snapshots, loading, error, refresh } = useBackups();
  const [busy, setBusy] = useState<"backup" | "restore" | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [flashKind, setFlashKind] = useState<"ok" | "err">("ok");
  const [restoreTarget, setRestoreTarget] = useState<Snapshot | null>(null);
  const [restoreConfirm, setRestoreConfirm] = useState("");

  function showFlash(message: string, kind: "ok" | "err" = "ok") {
    setFlash(message);
    setFlashKind(kind);
  }

  async function onBackupNow() {
    setBusy("backup");
    setFlash(null);
    try {
      const result = await createBackup();
      showFlash(`Backed up to ${snapshotLabel({ ...result, last_modified: result.finished_at, kind: "manual" } as Snapshot)} (${formatSize(result.size_bytes)})`);
      await refresh();
    } catch (e) {
      showFlash(e instanceof Error ? e.message : String(e), "err");
    } finally {
      setBusy(null);
    }
  }

  function openRestoreModal(snap: Snapshot) {
    setRestoreTarget(snap);
    setRestoreConfirm("");
  }

  async function onConfirmRestore() {
    if (!restoreTarget) return;
    setBusy("restore");
    setFlash(null);
    try {
      const result = await restoreBackup(restoreTarget.key);
      const safety = result.pre_restore_key ? ` (safety snapshot: ${snapshotLabel({ key: result.pre_restore_key } as Snapshot)})` : "";
      showFlash(`Restored from ${snapshotLabel(restoreTarget)}${safety}`);
      setRestoreTarget(null);
      await refresh();
    } catch (e) {
      showFlash(e instanceof Error ? e.message : String(e), "err");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <p className="loading">Loading...</p>;

  return (
    <div>
      <div className="page-heading">
        <h2>Backups</h2>
        <button
          className="btn-primary"
          onClick={onBackupNow}
          disabled={busy !== null}
        >
          {busy === "backup" ? "Backing up..." : "Backup now"}
        </button>
      </div>

      {error && <p className="flash flash-err">{error}</p>}
      {flash && <p className={`flash flash-${flashKind}`}>{flash}</p>}

      {snapshots.length === 0 ? (
        <p className="empty-state">No snapshots yet. Run "Backup now" to create one.</p>
      ) : (
        <table className="backup-table">
          <thead>
            <tr>
              <th>Snapshot</th>
              <th>Kind</th>
              <th>Size</th>
              <th>When</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((s) => (
              <tr key={s.key}>
                <td className="backup-key">{snapshotLabel(s)}</td>
                <td>
                  <span className={`backup-kind backup-kind-${s.kind}`}>{s.kind}</span>
                </td>
                <td>{formatSize(s.size_bytes)}</td>
                <td>{format(new Date(s.last_modified), "yyyy-MM-dd HH:mm")}</td>
                <td>
                  <button
                    className="btn-danger"
                    onClick={() => openRestoreModal(s)}
                    disabled={busy !== null}
                  >
                    Restore
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {restoreTarget && (
        <div className="modal-backdrop" onClick={() => busy === null && setRestoreTarget(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Restore from snapshot?</h3>
            <p className="modal-body">
              This will <strong>wipe the current database</strong> and replace it with the contents of:
            </p>
            <p className="modal-target">{snapshotLabel(restoreTarget)}</p>
            <p className="modal-body muted">
              A pre-restore safety snapshot will be taken automatically before the wipe.
              Bots will briefly lose their DB connections and reconnect.
            </p>
            <p className="modal-body">
              Type the snapshot timestamp to confirm:
            </p>
            <input
              type="text"
              className="modal-input"
              value={restoreConfirm}
              onChange={(e) => setRestoreConfirm(e.target.value)}
              placeholder={snapshotLabel(restoreTarget)}
              disabled={busy !== null}
              autoFocus
            />
            <div className="modal-actions">
              <button
                className="btn-secondary"
                onClick={() => setRestoreTarget(null)}
                disabled={busy !== null}
              >
                Cancel
              </button>
              <button
                className="btn-danger"
                onClick={onConfirmRestore}
                disabled={busy !== null || restoreConfirm !== snapshotLabel(restoreTarget)}
              >
                {busy === "restore" ? "Restoring..." : "Restore"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
