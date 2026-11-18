if (!Object.hasOwn(HTMLElement.prototype, "popover")) {
  import("https://unpkg.com/@oddbird/popover-polyfill@latest/dist/popover.min.js").catch(() => {});
}

export function initResponsiveNavbar() {
  const header = document.querySelector(".site-header");
  const inner = header?.querySelector(".header-inner");
  const menu = document.getElementById("site-menu");
  if (!header || !inner || !menu) return;

  let lastCollapsedWidth = 0;

  const measure = () => {
    const wasOpen = menu.matches(":popover-open") || menu.classList.contains(":popover-open");
    const currentWidth = header.clientWidth;

    if (!header.classList.contains("is-wide") && currentWidth <= lastCollapsedWidth) {
      return;
    }

    header.classList.add("is-measuring", "is-wide");
    menu.removeAttribute("popover");
    const fits = inner.scrollWidth <= inner.clientWidth;
    header.classList.toggle("is-wide", fits);

    if (!fits) {
      lastCollapsedWidth = currentWidth;
      menu.setAttribute("popover", "auto");
      if (wasOpen && typeof menu.showPopover === "function") {
        try {
          menu.showPopover();
        } catch {
          // Ignore if already open or unsupported
        }
      }
    } else {
      lastCollapsedWidth = 0;
      if (wasOpen && typeof menu.hidePopover === "function") {
        try {
          menu.hidePopover();
        } catch {
          // Ignore
        }
      }
    }

    requestAnimationFrame(() => {
      header.classList.remove("is-measuring");
    });
  };

  const observer = new ResizeObserver(() => measure());
  observer.observe(header);
  observer.observe(menu);
  measure();
}

document.addEventListener("DOMContentLoaded", initResponsiveNavbar);
