document.documentElement.classList.add("js");

const menuButton = document.querySelector(".menu-button");
const navigation = document.querySelector(".site-navigation");
const mobileNavigation = window.matchMedia("(max-width: 760px)");

if (menuButton && navigation) {
  const firstLink = navigation.querySelector("a");

  const closeMenu = ({ returnFocus = false } = {}) => {
    navigation.classList.remove("is-open");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.textContent = "Menu";
    if (returnFocus) {
      menuButton.focus();
    }
  };

  const openMenu = () => {
    navigation.classList.add("is-open");
    menuButton.setAttribute("aria-expanded", "true");
    menuButton.textContent = "Close";
    firstLink?.focus();
  };

  menuButton.addEventListener("click", () => {
    if (navigation.classList.contains("is-open")) {
      closeMenu({ returnFocus: true });
    } else {
      openMenu();
    }
  });

  navigation.addEventListener("click", (event) => {
    if (event.target instanceof HTMLAnchorElement) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navigation.classList.contains("is-open")) {
      closeMenu({ returnFocus: true });
    }
  });

  document.addEventListener("pointerdown", (event) => {
    if (
      navigation.classList.contains("is-open") &&
      event.target instanceof Node &&
      !navigation.contains(event.target) &&
      !menuButton.contains(event.target)
    ) {
      closeMenu();
    }
  });

  const closeAtDesktopWidth = (event) => {
    if (!event.matches) {
      closeMenu();
    }
  };

  mobileNavigation.addEventListener("change", closeAtDesktopWidth);
}
