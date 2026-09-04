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
