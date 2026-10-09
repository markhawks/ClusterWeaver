document.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-code");
  if (!button) return;
  const source = document.getElementById(button.dataset.target);
  const status = button.closest(".card-body, .card")?.querySelector(".copy-status, #copy-status");
  const copyWithSelection = (text) => {
    const temporary = document.createElement("textarea");
    temporary.value = text;
    temporary.setAttribute("readonly", "");
    temporary.style.position = "fixed";
    temporary.style.opacity = "0";
    document.body.appendChild(temporary);
    temporary.select();
    temporary.setSelectionRange(0, temporary.value.length);
    const copied = document.execCommand("copy");
    temporary.remove();
    return copied;
  };
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(source.textContent);
    } else if (!copyWithSelection(source.textContent)) {
      throw new Error("Legacy clipboard copy was rejected");
    }
    if (status) status.textContent = "Copied to clipboard.";
  } catch (_error) {
    try {
      if (!copyWithSelection(source.textContent)) throw new Error("Clipboard copy was rejected");
      if (status) status.textContent = "Copied to clipboard.";
    } catch (_fallbackError) {
      if (status) {
        status.textContent = "Copy failed. Select the text manually.";
        status.className = "small text-danger";
      }
    }
  }
});

document.addEventListener("click", (event) => {
  const button = event.target.closest(".expand-code");
  if (!button) return;
  const source = document.getElementById(button.dataset.codeTarget);
  const viewer = document.getElementById("script-viewer-code");
  const title = document.getElementById("script-viewer-title");
  if (!source || !viewer || !title) return;
  viewer.querySelector("code").textContent = source.textContent;
  title.textContent = button.dataset.scriptTitle;
  const status = document.querySelector("#script-viewer .copy-status");
  if (status) status.textContent = "";
});

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach((element) => {
    new bootstrap.Popover(element);
  });
  document.querySelectorAll(".collapse").forEach((panel) => {
    const selector = `[data-bs-target="#${panel.id}"]`;
    const toggle = document.querySelector(selector);
    if (!toggle || !toggle.classList.contains("collapse-toggle")) return;
    const isScript = toggle.textContent.trim().toLowerCase().includes("script");
    const summary = panel.closest(".workflow-script-area")?.querySelector(".workflow-run-summary");
    toggle.textContent = panel.classList.contains("show") ? (isScript ? "Hide script" : "Hide") : (isScript ? "Show script" : "Show");
    toggle.setAttribute("aria-expanded", panel.classList.contains("show") ? "true" : "false");
    panel.addEventListener("show.bs.collapse", () => { summary?.classList.add("d-none"); });
    panel.addEventListener("shown.bs.collapse", () => { toggle.textContent = isScript ? "Hide script" : "Hide"; });
    panel.addEventListener("hidden.bs.collapse", () => {
      toggle.textContent = isScript ? "Show script" : "Show";
      summary?.classList.remove("d-none");
    });
  });

  const major = document.getElementById("rhel_major");
  const minor = document.getElementById("rhel_minor");
  const releases = window.clusterWeaverRhelMinors;
  const platform = document.getElementById("platform_type");
  const hypervisor = document.getElementById("hypervisor");
  const hypervisorField = document.getElementById("hypervisor-field");
  const hardware = document.getElementById("hardware");
  const hardwareField = document.getElementById("hardware-field");
  if (platform && hypervisor && hypervisorField && hardware && hardwareField) {
    const updatePlatformFields = () => {
      const virtual = platform.value === "virtual";
      hypervisorField.classList.toggle("d-none", !virtual);
      hypervisor.disabled = !virtual;
      hypervisor.required = virtual;
      hardwareField.classList.toggle("d-none", virtual);
      hardware.disabled = virtual;
      hardware.required = !virtual;
    };
    platform.addEventListener("change", updatePlatformFields);
    updatePlatformFields();
  }
  if (!major || !minor || !releases) return;

  const initialMinor = minor.value;
  const updateMinorChoices = (preferLatest = false) => {
    const choices = releases[major.value] || [];
    const previous = preferLatest ? "" : minor.value || initialMinor;
    minor.replaceChildren(...choices.map((value) => new Option(`${major.value}.${value}`, value)));
    minor.value = choices.includes(previous) ? previous : choices.at(-1);
  };
  major.addEventListener("change", () => updateMinorChoices(true));
  updateMinorChoices(false);
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest(".remote-operation-form");
  if (!form) return;
  form.querySelector(".operation-progress")?.classList.remove("d-none");
  if (["stonith-profiles-form", "project-ssh-access-form"].includes(form.id)) {
    // Preserve the selected operation before disabling submit buttons.
    if (event.submitter?.name) {
      const action = document.createElement("input");
      action.type = "hidden";
      action.name = event.submitter.name;
      action.value = event.submitter.value;
      form.appendChild(action);
    }
    form.querySelectorAll('[type="submit"]').forEach((button) => { button.disabled = true; });
    return;
  }
  const submit = form.querySelector('[type="submit"]');
  if (submit) {
    submit.disabled = true;
    submit.value = "Running…";
  }
});

document.addEventListener("click", (event) => {
  const row = event.target.closest(".clickable-row[data-href]");
  if (!row || event.target.closest("a, button, input, select, textarea")) return;
  window.location.assign(row.dataset.href);
});

document.addEventListener("keydown", (event) => {
  const row = event.target.closest(".clickable-row[data-href]");
  if (!row || event.target.closest("a, button, input, select, textarea") || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  window.location.assign(row.dataset.href);
});

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("network-apply-form");
  const progress = document.getElementById("network-apply-progress");
  if (!form || !progress) return;
  form.addEventListener("submit", () => {
    const submit = form.querySelector('[type="submit"]');
    const selected = form.querySelector("#node_id option:checked")?.textContent || "selected node";
    const title = document.getElementById("network-apply-progress-title");
    const detail = document.getElementById("network-apply-progress-detail");
    const elapsed = document.getElementById("network-apply-elapsed");
    progress.classList.remove("d-none");
    title.textContent = `Configuring ${selected}…`;
    submit.disabled = true;
    submit.textContent = "Configuration running…";
    let seconds = 0;
    window.setInterval(() => {
      seconds += 1;
      elapsed.textContent = seconds;
      if (seconds >= 5) detail.textContent = "Applying NetworkManager profiles and waiting for SSH on the desired management IP.";
      if (seconds >= 20) detail.textContent = "Waiting for reconnection. The automatic rollback remains armed until SSH verification succeeds.";
    }, 1000);
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const suggestedGateway = (cidr) => {
    const match = cidr.trim().match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\/(\d|[12]\d|3[0-2])$/);
    if (!match) return null;
    const octets = match.slice(1, 5).map(Number);
    const prefix = Number(match[5]);
    if (octets.some((part) => part > 255) || prefix > 30) return null;
    const address = ((octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]) >>> 0;
    const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
    const gateway = ((address & mask) + 1) >>> 0;
    return [gateway >>> 24, (gateway >>> 16) & 255, (gateway >>> 8) & 255, gateway & 255].join(".");
  };

  document.querySelectorAll(".gateway-suggestion[data-address-source]").forEach((hint) => {
    const source = document.getElementById(hint.dataset.addressSource);
    const gateway = document.getElementById(hint.dataset.addressSource.replace("_ip", "_gateway"));
    if (!source || !gateway) return;
    const update = () => {
      const suggestion = suggestedGateway(source.value);
      hint.textContent = suggestion ? `Suggested gateway for this subnet: ${suggestion}.` : hint.dataset.defaultExample;
      gateway.placeholder = suggestion || gateway.dataset.defaultPlaceholder || gateway.placeholder;
    };
    gateway.dataset.defaultPlaceholder = gateway.placeholder;
    source.addEventListener("input", update);
    update();
  });

  const fqdn = document.getElementById("fqdn");
  const hostname = document.getElementById("hostname");
  const nodename = document.getElementById("nodename");
  if (!fqdn || !hostname || !nodename) return;

  let generatedHostname = hostname.value;
  let generatedNodename = `${hostname.value}lanc`;
  const updateFromFqdn = () => {
    const shortName = fqdn.value.trim().split(".")[0];
    if (!shortName) return;
    const nodenameWasGenerated = !nodename.value || nodename.value === generatedNodename;
    hostname.value = shortName;
    generatedHostname = shortName;
    generatedNodename = `${shortName}lanc`;
    if (nodenameWasGenerated) nodename.value = generatedNodename;
  };
  fqdn.addEventListener("input", updateFromFqdn);
  hostname.addEventListener("input", () => {
    if (!nodename.value || nodename.value === generatedNodename) {
      generatedHostname = hostname.value.trim();
      generatedNodename = `${generatedHostname}lanc`;
      nodename.value = generatedNodename;
    }
  });
});

// Track wall-clock time while the synchronous step 07 request is pending.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("cluster-setup-form");
  if (!form) return;
  form.addEventListener("submit", () => {
    const started = Date.now();
    const elapsed = document.getElementById("cluster-setup-elapsed");
    const warning = document.getElementById("cluster-setup-timeout-warning");
    const progress = form.querySelector(".operation-progress");
    window.setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      elapsed.textContent = seconds;
      if (seconds >= 150) {
        warning.classList.remove("d-none");
        progress.classList.replace("alert-info", "alert-warning");
        progress.querySelector(".spinner-border")?.classList.add("d-none");
      }
    }, 1000);
  });
});

// Background cluster operations: only read-only polling is repeated.
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('cluster-operations');
  if (!panel) return;
  const form = document.getElementById('cluster-operation-form');
  const actions = JSON.parse(panel.querySelector('[data-operation-actions]').textContent);
  const scripts = JSON.parse(panel.querySelector('[data-operation-scripts]').textContent);
  const nodes = JSON.parse(panel.querySelector('[data-operation-nodes]').textContent);
  const dialog = document.getElementById('cluster-operation-dialog');
  const progress = panel.querySelector('[data-cluster-progress]');
  const error = panel.querySelector('[data-cluster-error]');
  let jobs = JSON.parse(panel.querySelector('[data-operation-history]').textContent);
  let timer;
  let sending = false;
  const showError = message => { error.textContent = message; error.classList.remove('d-none'); };
  const clearError = () => { error.classList.add('d-none'); error.textContent = ''; };
  const command = (action, target) => ['standby', 'unstandby'].includes(action) ? `pcs node ${action} ${target}` : `pcs cluster ${action}`;
  const localDate = date => date ? new Date(date).toLocaleString('it-IT') : '—';
  function render() {
    const active = jobs.find(job => ['queued', 'running'].includes(job.status));
    const uncertain = jobs.find(job => job.action !== 'status' && job.status === 'unknown');
    const needsRefresh = uncertain && !jobs.some(job => job.action === 'status' && job.status === 'pass' && Date.parse(job.created_at) > Date.parse(uncertain.created_at));
    panel.querySelectorAll('[data-cluster-action]').forEach(button => {
      button.disabled = panel.dataset.ready !== 'true' || Boolean(active) || sending || (Boolean(needsRefresh) && button.dataset.clusterAction !== 'status');
    });
    if (active) {
      const elapsed = Math.max(0, Math.floor((Date.now() - Date.parse(active.created_at)) / 1000));
      progress.classList.remove('d-none');
      progress.textContent = `${actions[active.action][0]} · ${active.phase} · ${elapsed}s / ${active.budget}s`;
      if (elapsed > active.budget) progress.textContent += ' · Deadline exceeded: outcome requires verification.';
    } else if (needsRefresh) {
      progress.classList.remove('d-none');
      progress.textContent = 'The command outcome is uncertain. Successfully refresh cluster status before another modifying action.';
    } else {
      progress.classList.add('d-none');
    }
    const recent = jobs.find(job => job.results.length);
    const rows = recent?.results || [];
    const views = rows.filter(result => result.snapshot).map(result => result.snapshot);
    const quorum = views.length ? (views.every(view => view.quorum === true) ? 'Yes' : views.some(view => view.quorum === false) ? 'No / inconsistent' : 'not available') : 'not checked';
    panel.querySelector('[data-cluster-quorum]').textContent = quorum;
    const live = views.find(view => Object.keys(view.nodes).length)?.nodes;
    panel.querySelector('[data-cluster-online]').textContent = live ? `${Object.values(live).filter(node => node.online).length}/${nodes.length}` : 'not available';
    panel.querySelector('[data-cluster-updated]').textContent = localDate(recent?.finished_at || recent?.created_at);
    panel.querySelectorAll('[data-operation-node]').forEach(row => {
      const result = rows.find(item => String(item.node_id) === row.dataset.operationNode);
      const snapshot = result?.snapshot;
      row.querySelector('[data-node-services]').textContent = snapshot ? `${snapshot.services.pacemaker} / ${snapshot.services.corosync}` : result ? 'unreachable / unverified' : 'not checked';
      row.querySelector('[data-node-boot]').textContent = snapshot ? `${snapshot.boot.pacemaker} / ${snapshot.boot.corosync}` : 'not checked';
      const state = snapshot?.nodes[result.nodename];
      row.querySelector('[data-node-state]').textContent = state ? [state.online ? 'online' : 'offline', state.standby ? 'standby' : '', state.maintenance ? 'maintenance' : '', state.unclean ? 'unclean' : ''].filter(Boolean).join(' · ') : snapshot ? 'services stopped / no live view' : 'not checked';
    });
    panel.querySelector('[data-cluster-details]').textContent = rows.map(row => `${row.hostname} (${row.ip})\n${row.snapshot ? JSON.stringify({resources: row.snapshot.resources, failures: row.snapshot.failures}, null, 2) + '\n' + row.snapshot.details : row.output}`).join('\n\n') || 'No status collected.';
    const history = panel.querySelector('[data-cluster-history]');
    history.replaceChildren();
    if (!jobs.length) history.textContent = 'No operations recorded.';
    jobs.forEach(job => {
      const details = document.createElement('details');
      details.className = 'border rounded p-2 mb-2';
      const summary = document.createElement('summary');
      summary.textContent = `${localDate(job.created_at)} · ${job.username} · ${actions[job.action][0]}${job.target_node ? ' ' + job.target_node : ''} · ${job.status.toUpperCase()} · ${job.phase}`;
      details.appendChild(summary);
      job.results.forEach(result => {
        const pre = document.createElement('pre');
        pre.className = 'code-panel mt-2';
        pre.textContent = `${result.hostname} · ${result.ip} · ${result.phase} · ${result.state.toUpperCase()}\nCommand: ${result.command || 'read-only / already in requested state'}\nExit: ${result.command_exit ?? '—'}\n${result.output}`;
        details.appendChild(pre);
      });
      history.appendChild(details);
    });
  }
  async function poll() {
    clearTimeout(timer);
    try {
      const response = await fetch(panel.dataset.api, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Cannot read operation status. Reload the page; do not repeat a modifying command.');
      jobs = (await response.json()).jobs;
      render();
    } catch (exception) { showError(exception.message); }
    if (jobs.some(job => ['queued', 'running'].includes(job.status))) timer = setTimeout(poll, 2000);
  }
  async function submit(action, nodeId = '') {
    if (sending) return;
    sending = true;
    clearError();
    render();
    const data = new FormData(form);
    data.set('action', action);
    data.set('node_id', nodeId);
    if (action === 'status') data.delete('confirm');
    try {
      const response = await fetch(form.action, {method: 'POST', body: data, headers: {'Accept': 'application/json'}});
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Unexpected server response. Check operation history before retrying.');
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'Operation was rejected.');
      bootstrap.Modal.getInstance(dialog)?.hide();
      jobs.unshift(body);
      await poll();
    } catch (exception) {
      showError(exception.message);
      bootstrap.Modal.getInstance(dialog)?.hide();
      await poll(); // Read state only: the POST is never retried.
    } finally { sending = false; render(); }
  }
  panel.querySelectorAll('[data-cluster-action]').forEach(button => button.addEventListener('click', () => {
    const action = button.dataset.clusterAction;
    if (action === 'status') { submit(action); return; }
    form.querySelector('[name="action"]').value = action;
    form.querySelector('[name="node_id"]').value = button.dataset.nodeId || '';
    form.querySelector('[name="confirm"]').checked = false;
    dialog.querySelector('[data-operation-target]').textContent = button.dataset.nodeName ? `Selected node: ${button.dataset.nodeName}. SSH and identity preflight covers all project nodes.` : 'Affected nodes: ' + nodes.join(', ');
    dialog.querySelector('[data-operation-impact]').textContent = actions[action][1];
    dialog.querySelector('[data-operation-command]').textContent = command(action, button.dataset.nodeName || '');
    dialog.querySelector('[data-operation-script]').textContent = scripts[action + (button.dataset.nodeId ? ':' + button.dataset.nodeId : '')] || 'Configure nodenames before running this operation.';
    dialog.querySelector('[data-operation-submit]').className = 'btn btn-' + (action === 'stop' ? 'danger' : 'primary');
    dialog.querySelector('[data-operation-submit]').textContent = actions[action][0];
    bootstrap.Modal.getOrCreateInstance(dialog).show();
  }));
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.querySelector('[name="confirm"]').checked) {
      form.querySelector('[name="confirm"]').focus();
      return;
    }
    submit(form.querySelector('[name="action"]').value, form.querySelector('[name="node_id"]').value);
  });
  document.querySelector('[data-open-cluster-operations]')?.addEventListener('click', () => {
    bootstrap.Collapse.getOrCreateInstance(document.getElementById('cluster-operations-body'), {toggle: false}).show();
  });
  render();
  if (jobs.some(job => ['queued', 'running'].includes(job.status))) poll();
  setInterval(() => { if (jobs.some(job => ['queued', 'running'].includes(job.status))) render(); }, 1000);
});
