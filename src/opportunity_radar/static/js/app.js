"use strict";

const elements = {
  form: document.querySelector("#filters-form"),
  search: document.querySelector("#search-input"),
  company: document.querySelector("#company-filter"),
  category: document.querySelector("#category-filter"),
  location: document.querySelector("#location-filter"),
  clear: document.querySelector("#clear-filters"),
  emptyClear: document.querySelector("#empty-clear"),
  retry: document.querySelector("#retry-button"),
  count: document.querySelector("#results-count"),
  grid: document.querySelector("#opportunity-grid"),
  loading: document.querySelector("#loading-state"),
  empty: document.querySelector("#empty-state"),
  emptyTitle: document.querySelector("#empty-title"),
  emptyDescription: document.querySelector("#empty-description"),
  error: document.querySelector("#error-state"),
  errorDescription: document.querySelector("#error-description"),
};

let availableListings = 0;
let activeController = null;
let searchTimer = null;

function isDisplayableOpportunity(opportunity) {
  try {
    const url = new URL(opportunity.application_url);
    const host = url.hostname.toLowerCase();
    const isExampleDomain = host === "example.org" || host.endsWith(".example.org");
    return (url.protocol === "https:" || url.protocol === "http:") && !isExampleDomain;
  } catch {
    return false;
  }
}

async function requestOpportunities(params = new URLSearchParams(), signal) {
  const query = params.toString();
  const endpoint = query ? `/api/opportunities?${query}` : "/api/opportunities";
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`The Opportunity Radar API returned ${response.status}.`);
  }
  const opportunities = await response.json();
  if (!Array.isArray(opportunities)) {
    throw new Error("The Opportunity Radar API returned an unexpected response.");
  }
  return opportunities.filter(isDisplayableOpportunity);
}

function appendOptions(select, values, firstLabel) {
  select.replaceChildren(new Option(firstLabel, ""));
  for (const value of values) {
    select.add(new Option(value, value));
  }
}

function populateFilters(opportunities) {
  const companies = [...new Set(opportunities.map((item) => item.organization).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  const categories = [...new Set(opportunities.map((item) => item.category).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  const locations = [...new Set(opportunities.map((item) => item.location).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));

  appendOptions(elements.company, companies, "All companies");
  appendOptions(elements.location, locations, "All locations");
  elements.category.replaceChildren(new Option("All categories", ""));
  if (!categories.some((category) => category.toLowerCase() === "internship")) {
    elements.category.add(new Option("Internships", "Internship"));
  }
  for (const category of categories) {
    elements.category.add(new Option(category, category));
  }

  const internshipCategory = categories.find((category) => category.toLowerCase() === "internship");
  elements.category.value = internshipCategory || (categories.length === 0 ? "Internship" : "");
  availableListings = opportunities.length;
}

function formatDeadline(value) {
  if (!value) return "Deadline not listed";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function makeDetail(icon, label, value, extraClass = "") {
  const item = document.createElement("span");
  item.className = `detail-item ${extraClass}`.trim();
  item.innerHTML = icon;
  const text = document.createElement("span");
  text.textContent = value;
  if (extraClass === "deadline-value") text.className = extraClass;
  item.setAttribute("aria-label", `${label}: ${value}`);
  item.append(text);
  return item;
}

function createCard(opportunity, index) {
  const card = document.createElement("article");
  card.className = "opportunity-card";
  card.setAttribute("role", "listitem");
  card.style.animationDelay = `${Math.min(index * 45, 180)}ms`;

  const top = document.createElement("div");
  top.className = "card-topline";
  const category = document.createElement("span");
  category.className = "category-label";
  category.textContent = opportunity.category || "Opportunity";
  const source = document.createElement("span");
  source.className = "source-label";
  source.textContent = opportunity.source_name || "Verified employer source";
  top.append(category, source);

  const title = document.createElement("h3");
  title.textContent = opportunity.title;
  const organization = document.createElement("p");
  organization.className = "organization";
  organization.textContent = opportunity.organization || "Organization not listed";

  const details = document.createElement("div");
  details.className = "card-details";
  details.append(
    makeDetail(
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"></path><circle cx="12" cy="10" r="2.5"></circle></svg>',
      "Location",
      opportunity.location || "Location not listed",
    ),
    makeDetail(
      '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5.5" width="17" height="15" rx="2"></rect><path d="M7.5 3.5v4M16.5 3.5v4M3.5 10h17"></path></svg>',
      "Deadline",
      formatDeadline(opportunity.deadline),
      "deadline-value",
    ),
  );

  const footer = document.createElement("div");
  footer.className = "card-footer";
  const reference = document.createElement("span");
  reference.className = "card-reference";
  reference.textContent = "Apply with the original employer";
  const apply = document.createElement("a");
  apply.className = "apply-link";
  apply.href = opportunity.application_url;
  apply.target = "_blank";
  apply.rel = "noopener noreferrer";
  apply.append(document.createTextNode("Apply Now"));
  const arrow = document.createElement("span");
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "↗";
  apply.append(arrow);
  footer.append(reference, apply);

  card.append(top, title, organization, details, footer);
  return card;
}

function showLoading() {
  elements.loading.hidden = false;
  elements.grid.hidden = true;
  elements.empty.hidden = true;
  elements.error.hidden = true;
  elements.count.textContent = "Finding your opportunities…";
}

function showError(error) {
  elements.loading.hidden = true;
  elements.grid.hidden = true;
  elements.empty.hidden = true;
  elements.error.hidden = false;
  elements.count.textContent = "Opportunities unavailable";
  elements.errorDescription.textContent = error.message || "Please try again in a moment.";
}

function showEmpty() {
  elements.loading.hidden = true;
  elements.grid.hidden = true;
  elements.empty.hidden = false;
  elements.error.hidden = true;
  elements.count.textContent = "No opportunities found";
  const hasFilters = Boolean(
    elements.search.value.trim() || elements.company.value || elements.location.value ||
    (elements.category.value && elements.category.value !== "Internship"),
  );
  if (availableListings === 0 && !hasFilters) {
    elements.emptyTitle.textContent = "No internships in your radar just yet.";
    elements.emptyDescription.textContent = "Collect listings from your configured Greenhouse boards, then return to explore them here.";
  } else {
    elements.emptyTitle.textContent = "No opportunities match these filters.";
    elements.emptyDescription.textContent = "Try a different search or clear your filters to see more listings.";
  }
}

function showResults(opportunities) {
  elements.loading.hidden = true;
  elements.error.hidden = true;
  if (opportunities.length === 0) {
    showEmpty();
    return;
  }

  elements.empty.hidden = true;
  elements.grid.hidden = false;
  elements.grid.replaceChildren(...opportunities.map(createCard));
  elements.count.textContent = `${opportunities.length} ${opportunities.length === 1 ? "opportunity" : "opportunities"} in view`;
}

function currentFilters() {
  const params = new URLSearchParams();
  const query = elements.search.value.trim();
  const company = elements.company.value;
  const category = elements.category.value;
  const location = elements.location.value;
  if (query) params.set("q", query);
  if (company) params.set("company", company);
  if (category) params.set("category", category);
  if (location) params.set("location", location);
  return params;
}

async function loadResults() {
  if (activeController) activeController.abort();
  activeController = new AbortController();
  showLoading();
  try {
    const opportunities = await requestOpportunities(currentFilters(), activeController.signal);
    showResults(opportunities);
  } catch (error) {
    if (error.name !== "AbortError") showError(error);
  }
}

async function initialize() {
  if (activeController) activeController.abort();
  activeController = new AbortController();
  showLoading();
  try {
    const allOpportunities = await requestOpportunities(new URLSearchParams(), activeController.signal);
    populateFilters(allOpportunities);
    await loadResults();
  } catch (error) {
    if (error.name !== "AbortError") showError(error);
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (searchTimer) clearTimeout(searchTimer);
  loadResults();
});
elements.search.addEventListener("input", () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(loadResults, 260);
});
for (const filter of [elements.company, elements.category, elements.location]) {
  filter.addEventListener("change", loadResults);
}
for (const button of [elements.clear, elements.emptyClear]) {
  button.addEventListener("click", () => {
    elements.search.value = "";
    elements.company.value = "";
    elements.location.value = "";
    const internship = [...elements.category.options].find(
      (option) => option.value.toLowerCase() === "internship",
    );
    elements.category.value = internship ? internship.value : "";
    loadResults();
    elements.search.focus();
  });
}
elements.retry.addEventListener("click", initialize);

initialize();
