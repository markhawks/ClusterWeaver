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
    if (!toggle) return;
    const isScript = toggle.textContent.trim().toLowerCase().includes("script");
    const summary = panel.closest(".workflow-script-area")?.querySelector(".workflow-run-summary");
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
  if (platform && hypervisor && hypervisorField) {
    const updateHypervisor = () => {
      const virtual = platform.value === "virtual";
      hypervisorField.classList.toggle("d-none", !virtual);
      hypervisor.disabled = !virtual;
      hypervisor.required = virtual;
    };
    platform.addEventListener("change", updateHypervisor);
    updateHypervisor();
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
  if (!row || !["Enter", " "].includes(event.key)) return;
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
