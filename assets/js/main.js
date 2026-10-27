/* ===========================================================================
   A²M² — shared behaviour
   Plain ES2019+, no dependencies, no build step.
   =========================================================================== */

(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  var PROGRAMMES = {
    "brain-cognition": "Brain and cognition",
    "vision-eye-health-oculomics": "Vision, eye health and oculomics",
    "cancer-imaging-precision-oncology": "Cancer imaging and precision oncology",
    "vascular-health-healthy-ageing": "Vascular health and healthy ageing"
  };

  var TYPE_LABELS = {
    journal: "Journal",
    conference: "Conference",
    preprint: "Preprint",
    book: "Book chapter"
  };

  var TYPE_BADGES = {
    journal: ["JOUR", "NAL"],
    conference: ["CONF"],
    preprint: ["PRE", "PRINT"],
    book: ["BOOK"]
  };

  /* ---------------------------------------------------------------------
     Mobile navigation
     --------------------------------------------------------------------- */

  function initNav() {
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("primary-nav");
    if (!toggle || !nav) return;

    var MOBILE = "(max-width: 1000px)";

    function isOpen() {
      return nav.getAttribute("data-open") === "true";
    }

    function setOpen(open) {
      nav.setAttribute("data-open", open ? "true" : "false");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute(
        "aria-label",
        open ? "Close navigation menu" : "Open navigation menu"
      );
      document.body.style.overflow = open ? "hidden" : "";
    }

    setOpen(false);

    toggle.addEventListener("click", function () {
      setOpen(!isOpen());
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && isOpen()) {
        setOpen(false);
        toggle.focus();
      }
    });

    document.addEventListener("click", function (event) {
      if (!isOpen()) return;
      if (nav.contains(event.target) || toggle.contains(event.target)) return;
      setOpen(false);
    });

    nav.addEventListener("click", function (event) {
      if (event.target.closest("a") && isOpen()) setOpen(false);
    });

    var mq = window.matchMedia(MOBILE);
    var onChange = function (event) {
      if (!event.matches) setOpen(false);
    };
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(onChange);
    }
  }

  /* ---------------------------------------------------------------------
     Reveal on scroll
     --------------------------------------------------------------------- */

  function initReveal() {
    var targets = Array.prototype.slice.call(
      document.querySelectorAll("[data-reveal]")
    );
    if (!targets.length) return;

    if (!("IntersectionObserver" in window) || prefersReducedMotion) {
      targets.forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }

    document
      .querySelectorAll("[data-reveal-group]")
      .forEach(function (group) {
        Array.prototype.slice
          .call(group.querySelectorAll("[data-reveal]"))
          .forEach(function (el, index) {
            el.style.setProperty(
              "--reveal-delay",
              Math.min(index, 6) * 70 + "ms"
            );
          });
      });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );

    targets.forEach(function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.92) {
        el.classList.add("is-visible");
      } else {
        observer.observe(el);
      }
    });
  }

  /* ---------------------------------------------------------------------
     Publications
     The canonical records live in assets/data/publications.json. Only fields
     explicitly marked as verified may be rendered as collaborator details.
     --------------------------------------------------------------------- */

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function createElement(tagName, className, text) {
    var element = document.createElement(tagName);
    if (className) element.className = className;
    if (typeof text === "string") element.textContent = text;
    return element;
  }

  function isSafeUrl(value) {
    if (typeof value !== "string" || !value) return false;
    try {
      var parsed = new URL(value, window.location.href);
      return parsed.protocol === "https:" || parsed.protocol === "http:";
    } catch (error) {
      return false;
    }
  }

  function validProgrammeTags(tags) {
    if (!Array.isArray(tags)) return [];
    return tags.filter(function (tag) {
      return Object.prototype.hasOwnProperty.call(PROGRAMMES, tag);
    });
  }

  function validatePublication(record) {
    if (!record || typeof record !== "object") return null;
    if (typeof record.id !== "string" || !record.id) return null;
    if (typeof record.title !== "string" || !record.title) return null;
    if (typeof record.year !== "number" || !Number.isFinite(record.year)) {
      return null;
    }
    if (!Object.prototype.hasOwnProperty.call(TYPE_LABELS, record.type)) {
      return null;
    }
    if (!Array.isArray(record.authors) || !record.authors.length) return null;
    if (typeof record.venue !== "string" || !record.venue) return null;
    if (!isSafeUrl(record.url)) return null;

    var authors = record.authors
      .filter(function (author) {
        return author && typeof author.name === "string" && author.name;
      })
      .map(function (author) {
        return { name: author.name, groupMember: author.groupMember === true };
      });
    if (!authors.length) return null;

    var links = Array.isArray(record.links)
      ? record.links.filter(function (link) {
          return link && typeof link.label === "string" && isSafeUrl(link.url);
        })
      : [];

    var verifiedCollaborators = Array.isArray(record.collaborators)
      ? record.collaborators.filter(function (collaborator) {
          return (
            collaborator &&
            collaborator.verified === true &&
            typeof collaborator.name === "string" &&
            collaborator.name
          );
        })
      : [];

    return {
      id: record.id,
      anchorId:
        typeof record.anchorId === "string" && record.anchorId
          ? record.anchorId
          : record.id,
      title: record.title,
      year: record.year,
      yearGroup:
        typeof record.yearGroup === "string" && record.yearGroup
          ? record.yearGroup
          : String(record.year),
      type: record.type,
      authors: authors,
      venue: record.venue,
      url: record.url,
      links: links,
      programmeTags: validProgrammeTags(record.programmeTags),
      featuredOrder:
        Number.isInteger(record.featuredOrder) && record.featuredOrder > 0
          ? record.featuredOrder
          : null,
      collaborators: verifiedCollaborators
    };
  }

  function loadPublications(source) {
    return window
      .fetch(source, { cache: "no-cache" })
      .then(function (response) {
        if (!response.ok) throw new Error("Publication data could not be loaded.");
        return response.json();
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.publications)) {
          throw new Error("Publication data has an invalid format.");
        }

        var seenIds = {};
        var publications = data.publications
          .map(validatePublication)
          .filter(function (record) {
            if (!record || seenIds[record.id]) return false;
            seenIds[record.id] = true;
            return true;
          });

        if (!publications.length) {
          throw new Error("No valid publication records were found.");
        }

        return publications.sort(function (a, b) {
          if (b.year !== a.year) return b.year - a.year;
          return a.title.localeCompare(b.title);
        });
      });
  }

  function appendBadge(badge, type) {
    var parts = TYPE_BADGES[type] || [TYPE_LABELS[type].toUpperCase()];
    badge.setAttribute("aria-label", TYPE_LABELS[type]);
    parts.forEach(function (part, index) {
      if (index) badge.appendChild(document.createElement("br"));
      badge.appendChild(document.createTextNode(part));
    });
  }

  function appendAuthors(container, authors) {
    authors.forEach(function (author, index) {
      if (index) container.appendChild(document.createTextNode(", "));
      var authorNode = createElement(
        "span",
        author.groupMember ? "is-group" : "",
        author.name
      );
      container.appendChild(authorNode);
    });
  }

  function renderProgrammeTags(record) {
    if (!record.programmeTags.length) return null;

    var row = createElement("div", "tag-row pub__programmes");
    record.programmeTags.forEach(function (tag, index) {
      var link = createElement(
        "a",
        "tag" + (index % 2 ? " tag--teal" : " tag--brand"),
        PROGRAMMES[tag]
      );
      link.href = "research.html#" + tag;
      row.appendChild(link);
    });
    return row;
  }

  function renderCollaborators(record) {
    if (!record.collaborators.length) return null;

    var container = createElement("p", "pub__collaborators");
    container.appendChild(document.createTextNode("Collaborators: "));
    record.collaborators.forEach(function (collaborator, index) {
      if (index) container.appendChild(document.createTextNode(" · "));
      container.appendChild(document.createTextNode(collaborator.name));
      if (typeof collaborator.affiliation === "string" && collaborator.affiliation) {
        container.appendChild(
          document.createTextNode(" (" + collaborator.affiliation + ")")
        );
      }
    });
    return container;
  }

  function renderPublicationCard(record, compact) {
    var article = createElement("article", "pub");
    article.id = record.anchorId;
    article.dataset.year = record.yearGroup;
    article.dataset.type = record.type;
    article.dataset.programmes = record.programmeTags.join(" ");

    var badge = createElement("span", "pub__badge");
    appendBadge(badge, record.type);
    article.appendChild(badge);

    var body = document.createElement("div");
    var title = createElement("h3", "pub__title");
    var titleLink = createElement("a", "", record.title);
    titleLink.href = record.url;
    title.appendChild(titleLink);
    body.appendChild(title);

    var authors = createElement("p", "pub__authors");
    appendAuthors(authors, record.authors);
    body.appendChild(authors);

    body.appendChild(createElement("p", "pub__venue", record.venue));

    var programmes = renderProgrammeTags(record);
    if (programmes) body.appendChild(programmes);

    var collaborators = renderCollaborators(record);
    if (collaborators) body.appendChild(collaborators);

    if (!compact && record.links.length) {
      var links = createElement("div", "pub__links");
      record.links.forEach(function (link) {
        var linkNode = createElement("a", "", link.label + " ↗");
        linkNode.href = link.url;
        links.appendChild(linkNode);
      });
      body.appendChild(links);
    }

    article.appendChild(body);
    return article;
  }

  function sortYearGroups(records) {
    var groups = {};
    records.forEach(function (record) {
      if (!groups[record.yearGroup]) groups[record.yearGroup] = [];
      groups[record.yearGroup].push(record);
    });

    return Object.keys(groups)
      .sort(function (a, b) {
        if (a === "earlier") return 1;
        if (b === "earlier") return -1;
        return Number(b) - Number(a);
      })
      .map(function (group) {
        return { key: group, label: group === "earlier" ? "Earlier" : group, records: groups[group] };
      });
  }

  function setStatus(node, message) {
    if (!node) return;
    node.textContent = message;
    node.hidden = !message;
  }

  function createFilterButtons(container, label, filterName, options, state, apply) {
    clearNode(container);
    var legend = createElement("legend", "filter-group__label", label);
    container.appendChild(legend);

    options.forEach(function (option) {
      var button = createElement("button", "chip", option.label);
      button.type = "button";
      button.dataset.filter = filterName;
      button.dataset.value = option.value;
      button.setAttribute(
        "aria-pressed",
        state[filterName] === option.value ? "true" : "false"
      );
      button.addEventListener("click", function () {
        state[filterName] = option.value;
        Array.prototype.slice.call(container.querySelectorAll("button")).forEach(
          function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
          }
        );
        apply();
      });
      container.appendChild(button);
    });
  }

  function initPublicationCatalog(component, records) {
    var results = component.querySelector("#pub-results");
    var toolbar = component.querySelector("#pub-toolbar");
    var yearFilters = component.querySelector("#pub-year-filters");
    var typeFilters = component.querySelector("#pub-type-filters");
    var programmeFilters = component.querySelector("#pub-programme-filters");
    var searchInput = component.querySelector("#pub-search");
    var emptyState = component.querySelector("#pub-empty");
    var countOutput = component.querySelector("#pub-count");
    var status = component.querySelector("#pub-load-status");

    if (!results || !toolbar || !yearFilters || !typeFilters || !programmeFilters) {
      return;
    }

    var requestedProgramme = new URLSearchParams(window.location.search).get(
      "programme"
    );
    var state = {
      year: "all",
      type: "all",
      programme: Object.prototype.hasOwnProperty.call(PROGRAMMES, requestedProgramme)
        ? requestedProgramme
        : "all",
      query: ""
    };

    var yearOptions = [{ value: "all", label: "All" }].concat(
      sortYearGroups(records).map(function (group) {
        return { value: group.key, label: group.label };
      })
    );
    var typeOptions = [{ value: "all", label: "All" }].concat(
      Object.keys(TYPE_LABELS)
        .filter(function (type) {
          return records.some(function (record) {
            return record.type === type;
          });
        })
        .map(function (type) {
          return { value: type, label: TYPE_LABELS[type] };
        })
    );
    var programmeOptions = [{ value: "all", label: "All" }].concat(
      Object.keys(PROGRAMMES)
        .filter(function (programme) {
          return records.some(function (record) {
            return record.programmeTags.indexOf(programme) !== -1;
          });
        })
        .map(function (programme) {
          return { value: programme, label: PROGRAMMES[programme] };
        })
    );

    function matches(record) {
      if (state.year !== "all" && record.yearGroup !== state.year) return false;
      if (state.type !== "all" && record.type !== state.type) return false;
      if (
        state.programme !== "all" &&
        record.programmeTags.indexOf(state.programme) === -1
      ) {
        return false;
      }

      var haystack = [
        record.title,
        record.venue,
        record.authors.map(function (author) { return author.name; }).join(" "),
        record.programmeTags.map(function (tag) { return PROGRAMMES[tag]; }).join(" "),
        record.collaborators
          .map(function (collaborator) {
            return collaborator.name + " " + (collaborator.affiliation || "");
          })
          .join(" ")
      ]
        .join(" ")
        .toLowerCase();

      return !state.query || haystack.indexOf(state.query) !== -1;
    }

    function render() {
      clearNode(results);
      var visibleRecords = records.filter(matches);

      sortYearGroups(visibleRecords).forEach(function (group) {
        var groupSection = createElement("section", "pub-group");
        var year = createElement("div", "pub-year");
        year.appendChild(createElement("h2", "", group.label));
        groupSection.appendChild(year);

        var list = createElement("div", "pub-list");
        group.records.forEach(function (record) {
          list.appendChild(renderPublicationCard(record, false));
        });
        groupSection.appendChild(list);
        results.appendChild(groupSection);
      });

      if (emptyState) emptyState.hidden = visibleRecords.length !== 0;
      if (countOutput) {
        countOutput.textContent =
          visibleRecords.length === records.length
            ? records.length + " publications"
            : visibleRecords.length + " of " + records.length + " publications";
      }
      setStatus(status, "");
    }

    createFilterButtons(yearFilters, "Year", "year", yearOptions, state, render);
    createFilterButtons(typeFilters, "Type", "type", typeOptions, state, render);
    createFilterButtons(
      programmeFilters,
      "Programme",
      "programme",
      programmeOptions,
      state,
      render
    );

    if (searchInput) {
      var timer = null;
      searchInput.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
          state.query = searchInput.value.trim().toLowerCase();
          render();
        }, 140);
      });
    }

    toolbar.hidden = false;
    results.setAttribute("aria-busy", "false");
    render();
  }

  function initFeaturedPublications(root, records) {
    var limit = Number(root.dataset.featuredLimit) || 3;
    var featured = records
      .filter(function (record) {
        return record.featuredOrder !== null;
      })
      .sort(function (a, b) {
        return a.featuredOrder - b.featuredOrder;
      })
      .slice(0, limit);

    clearNode(root);
    featured.forEach(function (record) {
      root.appendChild(renderPublicationCard(record, true));
    });
  }

  function initPublications() {
    var catalog = document.getElementById("publications-component");
    var featured = document.querySelector("[data-featured-publications]");
    if (!catalog && !featured) return;

    var source =
      (catalog && catalog.dataset.publicationsSource) ||
      (featured && featured.dataset.publicationsSource) ||
      "assets/data/publications.json";

    var status = catalog && catalog.querySelector("#pub-load-status");
    var results = catalog && catalog.querySelector("#pub-results");
    var error = catalog && catalog.querySelector("#pub-load-error");
    if (results) results.setAttribute("aria-busy", "true");
    setStatus(status, "Loading publications…");

    loadPublications(source)
      .then(function (records) {
        if (catalog) initPublicationCatalog(catalog, records);
        if (featured) initFeaturedPublications(featured, records);
      })
      .catch(function () {
        if (results) results.setAttribute("aria-busy", "false");
        if (error) error.hidden = false;
        setStatus(status, "");
        if (featured) {
          clearNode(featured);
          featured.appendChild(
            createElement(
              "p",
              "pub-load-error",
              "Featured publications are temporarily unavailable."
            )
          );
        }
      });
  }

  /* ---------------------------------------------------------------------
     Research community
     The community record is intentionally separate from publications: it
     contains only approved public research people, selected student topics,
     alumni and selected relevant funding.
     --------------------------------------------------------------------- */

  function communityProgrammeLabel(programme) {
    if (Object.prototype.hasOwnProperty.call(PROGRAMMES, programme)) {
      return PROGRAMMES[programme];
    }
    if (programme === "clinical-reporting") return "Clinical reporting";
    return "Research community";
  }

  function createCommunityIcon(name) {
    var icons = {
      brain: [
        ["path", "M12 3C8 3 5 6 5 10c0 2.6 1.3 4.7 3.4 6.1V20h7.2v-3.9C17.7 14.7 19 12.6 19 10c0-4-3-7-7-7Z"],
        ["path", "M9 20h6M10 8h4M12 6v4"]
      ],
      eye: [
        ["path", "M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"],
        ["circle", "12", "12", "2.5"]
      ],
      cancer: [
        ["circle", "12", "12", "8"],
        ["circle", "12", "12", "3"],
        ["path", "m16 8 5-5"]
      ],
      vascular: [
        ["path", "M3 12h3l2.5-7 3 14 3-9 2 4h6.5"],
        ["path", "M18 4v4M16 6h4"]
      ],
      report: [
        ["path", "M4 4h16v14H8l-4 4V4Z"],
        ["path", "M8 8h8M8 12h6"]
      ]
    };
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.7");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");

    (icons[name] || icons.report).forEach(function (shape) {
      var node = document.createElementNS("http://www.w3.org/2000/svg", shape[0]);
      if (shape[0] === "circle") {
        node.setAttribute("cx", shape[1]);
        node.setAttribute("cy", shape[2]);
        node.setAttribute("r", shape[3]);
      } else {
        node.setAttribute("d", shape[1]);
      }
      svg.appendChild(node);
    });
    return svg;
  }

  function appendCommunityProgramme(row, programme, tone) {
    var label = communityProgrammeLabel(programme);
    if (Object.prototype.hasOwnProperty.call(PROGRAMMES, programme)) {
      var link = createElement("a", "tag " + tone, label);
      link.href = "research.html#" + programme;
      row.appendChild(link);
    } else {
      row.appendChild(createElement("span", "tag " + tone, label));
    }
  }

  function renderCommunityCard(item, kind, index) {
    var card = createElement("article", "card pillar");
    card.id = item.id;

    var icon = createElement("span", "pillar__icon");
    icon.setAttribute("aria-hidden", "true");
    icon.appendChild(createCommunityIcon(item.icon));
    card.appendChild(icon);

    if (kind === "project") {
      card.appendChild(createElement("p", "pillar__num", String(index + 1).padStart(2, "0")));
    } else if (item.role || item.degree) {
      card.appendChild(createElement("p", "person__role", item.role || item.degree));
    }

    card.appendChild(createElement("h3", "", item.name || item.title));

    var tags = createElement("div", "tag-row");
    var tone = index % 2 ? "tag--teal" : "tag--brand";
    if (item.programme) appendCommunityProgramme(tags, item.programme, tone);
    if (kind === "project") {
      tags.appendChild(createElement("span", "tag " + tone, item.degree));
      tags.appendChild(createElement("span", "tag " + tone, item.period));
    } else if (kind === "funding") {
      tags.appendChild(createElement("span", "tag " + tone, item.funder));
      tags.appendChild(createElement("span", "tag " + tone, item.period));
      tags.appendChild(createElement("span", "tag " + tone, item.status));
    }
    if (tags.childNodes.length) card.appendChild(tags);

    card.appendChild(createElement("p", "", item.topic || item.description));

    if (item.supervisors && item.supervisors.length) {
      card.appendChild(createElement("p", "community-meta", "Supervisors: " + item.supervisors.join(", ")));
    }
    if (item.completionYear) {
      card.appendChild(createElement("p", "community-meta", "Completed: " + item.completionYear));
    }
    if (isSafeUrl(item.url)) {
      var link = createElement("a", "arrow-link", "Project record →");
      link.href = item.url;
      card.appendChild(link);
    }
    return card;
  }

  function validCommunityRecord(item, kind) {
    if (!item || typeof item !== "object" || typeof item.id !== "string") return null;
    var title = kind === "person" || kind === "alumni" ? item.name : item.title;
    var detail = kind === "person" || kind === "alumni" ? item.topic : item.description;
    if (typeof title !== "string" || !title || typeof detail !== "string" || !detail) return null;
    if (typeof item.programme !== "string" || !item.programme) return null;
    return item;
  }

  function renderCommunitySection(root, items, kind) {
    clearNode(root);
    items.forEach(function (item, index) {
      var record = validCommunityRecord(item, kind);
      if (record) root.appendChild(renderCommunityCard(record, kind, index));
    });
    return root.childNodes.length;
  }

  function initCommunity() {
    var component = document.getElementById("community-component");
    if (!component) return;

    var source = component.dataset.communitySource || "assets/data/community.json";
    var status = component.querySelector("#community-load-status");
    var error = component.querySelector("#community-load-error");
    var sections = {
      current: component.querySelector("[data-community-current]"),
      projects: component.querySelector("[data-community-projects]"),
      alumni: component.querySelector("[data-community-alumni]"),
      funding: component.querySelector("[data-community-funding]")
    };

    setStatus(status, "Loading research community…");
    window
      .fetch(source, { cache: "no-cache" })
      .then(function (response) {
        if (!response.ok) throw new Error("Community data could not be loaded.");
        return response.json();
      })
      .then(function (data) {
        if (!data || typeof data !== "object") throw new Error("Invalid community data.");
        if (sections.current) renderCommunitySection(sections.current, Array.isArray(data.currentPhdResearchers) ? data.currentPhdResearchers : [], "person");
        if (sections.projects) renderCommunitySection(sections.projects, Array.isArray(data.selectedProjects) ? data.selectedProjects : [], "project");
        if (sections.funding) renderCommunitySection(sections.funding, Array.isArray(data.fundedProjects) ? data.fundedProjects : [], "funding");
        if (sections.alumni) {
          var alumniCount = renderCommunitySection(sections.alumni, Array.isArray(data.alumni) ? data.alumni : [], "alumni");
          var alumniSection = sections.alumni.closest("section");
          if (alumniSection) alumniSection.hidden = alumniCount === 0;
        }
        setStatus(status, "");
      })
      .catch(function () {
        if (error) error.hidden = false;
        setStatus(status, "");
      });
  }

  /* ---------------------------------------------------------------------
     Footer year
     --------------------------------------------------------------------- */

  function initYear() {
    document.querySelectorAll("[data-current-year]").forEach(function (el) {
      el.textContent = String(new Date().getFullYear());
    });
  }

  function boot() {
    document.documentElement.classList.remove("no-js");
    initNav();
    initReveal();
    initPublications();
    initCommunity();
    initYear();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
