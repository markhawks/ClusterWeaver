document.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-code");
  if (!button) return;
  const source = document.getElementById(button.dataset.target);
  const status = document.getElementById("copy-status");
  try {
    await navigator.clipboard.writeText(source.textContent);
    status.textContent = "Copied to clipboard.";
  } catch (_error) {
    status.textContent = "Copy failed. Select the text manually.";
    status.className = "small text-danger";
  }
});

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach((element) => {
    new bootstrap.Popover(element);
  });

  const major = document.getElementById("rhel_major");
  const minor = document.getElementById("rhel_minor");
  const releases = window.clusterWeaverRhelMinors;
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
