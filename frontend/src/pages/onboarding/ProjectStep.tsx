import { useEffect, useState, type FormEvent } from 'react'
import { useAvailableDomains, useCreateOrganization, useCreateProject, useMe } from '../../api/hooks'
import { useActiveProject } from '../../state/ActiveProjectContext'
import { formatValidationErrors } from './validationError'

export function ProjectStep() {
  const { projects, activeProjectId, setActiveProjectId } = useActiveProject()
  const me = useMe()
  const domainsQuery = useAvailableDomains()
  const createOrg = useCreateOrganization()
  const createProject = useCreateProject()

  const memberships = me.data?.memberships ?? []

  // `me` loads asynchronously, so `projects` is transiently [] on first
  // render even for a team with existing projects -- track whether the
  // user has manually toggled the create form so the real, loaded
  // project count (not the pre-fetch placeholder) decides the default,
  // without fighting a deliberate open/close from the user afterwards.
  const [creating, setCreating] = useState(false)
  const [userToggled, setUserToggled] = useState(false)
  const [orgName, setOrgName] = useState('')
  const [selectedOrgId, setSelectedOrgId] = useState('')
  const [projectName, setProjectName] = useState('')
  const [projectDomain, setProjectDomain] = useState('')
  const [errors, setErrors] = useState<string[] | null>(null)

  useEffect(() => {
    if (!userToggled && !me.isLoading) setCreating(projects.length === 0)
  }, [projects.length, me.isLoading, userToggled])

  function setCreatingManually(value: boolean) {
    setUserToggled(true)
    setCreating(value)
  }

  useEffect(() => {
    if (!selectedOrgId && memberships.length > 0) setSelectedOrgId(memberships[0].org_id)
  }, [memberships, selectedOrgId])

  useEffect(() => {
    if (!projectDomain && domainsQuery.data && domainsQuery.data.length > 0) setProjectDomain(domainsQuery.data[0])
  }, [domainsQuery.data, projectDomain])

  const uniqueOrgIds = Array.from(new Set(memberships.map((m) => m.org_id)))

  async function handleCreateOrg(e: FormEvent) {
    e.preventDefault()
    setErrors(null)
    try {
      const org = await createOrg.mutateAsync(orgName)
      setSelectedOrgId(org.org_id)
      setOrgName('')
    } catch (err) {
      setErrors(formatValidationErrors(err))
    }
  }

  async function handleCreateProject(e: FormEvent) {
    e.preventDefault()
    setErrors(null)
    try {
      const project = await createProject.mutateAsync({ orgId: selectedOrgId, name: projectName, domain: projectDomain })
      setActiveProjectId(project.project_id)
      setProjectName('')
      setCreatingManually(false)
    } catch (err) {
      setErrors(formatValidationErrors(err))
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Project &amp; domain</h2>
        <p>Choose which project you're configuring, or create a new one. Each project belongs to one domain and holds its own metrics, guardrails, and data.</p>
      </div>

      {projects.length > 0 && (
        <div className="inline-list" style={{ marginBottom: 16 }}>
          {projects.map((p) => (
            <div
              key={p.project_id}
              className={`selectable-card${p.project_id === activeProjectId ? ' selected' : ''}`}
              onClick={() => setActiveProjectId(p.project_id)}
              role="radio"
              aria-checked={p.project_id === activeProjectId}
              tabIndex={0}
            >
              <div>
                <strong>{p.name}</strong>
                <div className="text-muted" style={{ fontSize: 12 }}>{p.domain}</div>
              </div>
              {p.project_id === activeProjectId && <span className="chip chip-accent">Active</span>}
            </div>
          ))}
        </div>
      )}

      {!creating && (
        <button type="button" className="btn btn-small" onClick={() => setCreatingManually(true)}>
          + Create a new project
        </button>
      )}

      {creating && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: projects.length > 0 ? 16 : 0 }}>
          {memberships.length === 0 ? (
            <form onSubmit={handleCreateOrg} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <p className="text-secondary" style={{ fontSize: 12.5 }}>You don't belong to an organization yet -- create one to hold your projects.</p>
              <label className="field">
                <span>Organization name</span>
                <input value={orgName} onChange={(e) => setOrgName(e.target.value)} required autoFocus />
              </label>
              <button type="submit" className="btn btn-primary" disabled={createOrg.isPending} style={{ alignSelf: 'flex-start' }}>
                {createOrg.isPending ? 'Creating…' : 'Create organization'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleCreateProject} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {uniqueOrgIds.length > 1 && (
                <label className="field">
                  <span>Organization</span>
                  <select value={selectedOrgId} onChange={(e) => setSelectedOrgId(e.target.value)}>
                    {uniqueOrgIds.map((id) => (
                      <option key={id} value={id}>{id.slice(0, 8)}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="field">
                <span>Project name</span>
                <input value={projectName} onChange={(e) => setProjectName(e.target.value)} required autoFocus />
              </label>
              <label className="field">
                <span>Domain</span>
                <select value={projectDomain} onChange={(e) => setProjectDomain(e.target.value)}>
                  {(domainsQuery.data ?? []).map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="submit" className="btn btn-primary" disabled={createProject.isPending}>
                  {createProject.isPending ? 'Creating…' : 'Create project'}
                </button>
                {projects.length > 0 && (
                  <button type="button" className="btn" onClick={() => setCreatingManually(false)}>Cancel</button>
                )}
              </div>
            </form>
          )}
        </div>
      )}

      {errors && (
        <div className="chip chip-negative" style={{ alignSelf: 'flex-start', marginTop: 12, whiteSpace: 'pre-wrap' }}>
          {errors.join('; ')}
        </div>
      )}
    </div>
  )
}
