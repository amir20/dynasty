import Vue from "vue";
import Vuex from "vuex";
import camelCase from "lodash/camelCase";
import reduce from "lodash/reduce";
import keyBy from "lodash/keyBy";
import { event } from "../ga";

Vue.use(Vuex);

const state = {
  tag: null,
  loading: true,
  clan: window.__CLAN__ || [],
  previousData: window.__CLAN__ || [],
  lastUpdated: new Date(window.__LAST_UPDATED__) || null,
  playersStatus: {},
  days: 7,
  similarClansAvg: {},
  savedClanStats: {},
  clanStats: {},
  daysSpan: 7,
  sortField: "value",
  apiError: null
};

const mutations = {
  setTag(state, tag) {
    state.tag = tag;
  },
  setRefreshData(state, data) {
    state.clan = data.playerData;
    state.playersStatus = data.playersStatus;
    state.lastUpdated = new Date();
  },
  setClanStats(state, data) {
    state.clanStats = data;
  },
  setPreviousData(state, previousData) {
    state.previousData = previousData;
  },
  setDays(state, days) {
    state.days = days;
  },
  setSimilarClansAvg(state, similarClansAvg) {
    state.similarClansAvg = similarClansAvg;
  },
  startLoading(state) {
    state.loading = true;
  },
  stopLoading(state) {
    state.loading = false;
  },
  setDaysSpan(state, daysSpan) {
    state.daysSpan = daysSpan;
  },
  setSortField(state, field) {
    event("sort-field", "Change Sort Field");
    state.sortField = field;
  },
  setApiError(state, field) {
    state.apiError = field;
  },
  setSavedClanStats(state, field) {
    state.savedClanStats = field;
  }
};

async function handleResponse(promise, commit, success, error = "setApiError") {
  const response = await promise;
  if (response.status == 200) {
    const data = await response.json();
    commit(success, data);
  } else {
    const e = await response.json();
    e.status = response.status;
    console.warn(`Error while fetch data from API. Status: ${e.status}, Message: ${e.error}`);
    if (error) {
      commit(error, e);
    }
  }
}

const actions = {
  async fetchClanData({ commit, dispatch, getters: { path } }) {
    const refreshPromise = fetch(`${path}/refresh.json`);
    const previousPromise = fetch(`${path}.json?daysAgo=${state.days}`);
    const clanStatsPromise = await fetch(`${path}/stats.json`);
    commit("stopLoading");
    await handleResponse(previousPromise, commit, "setPreviousData");
    await handleResponse(refreshPromise, commit, "setRefreshData");
    await handleResponse(clanStatsPromise, commit, "setClanStats");

    dispatch("fetchSimilarClansStats");
    dispatch("fetchSavedClanStats");
  },
  async fetchSimilarClansStats({ commit, getters: { path } }) {
    const similarClansPromise = await fetch(`${path}/similar/avg.json`);
    await handleResponse(similarClansPromise, commit, "setSimilarClansAvg");
  },
  async fetchSavedClanStats({ commit, state: { tag, days } }) {
    const savedTag = localStorage.getItem("lastTag");
    if (savedTag && savedTag != tag) {
      console.log(`Found saved tag value [${savedTag}].`);
      const savedClanStatsPromise = await fetch(`/clan/${savedTag.replace("#", "")}/stats.json?daysAgo=${days}`);
      await handleResponse(savedClanStatsPromise, commit, "setSavedClanStats", false);
    }
  },
  async loadDaysAgo(
    {
      commit,
      dispatch,
      getters: { path }
    },
    days
  ) {
    event("days-ago", "Change Days", "Days", days);
    commit("setDays", days);
    commit("startLoading");
    const promise = await fetch(`${path}.json?daysAgo=${days}`);
    const clanStatsPromise = await fetch(`${path}/stats.json?daysAgo=${days}`);
    const similarClansPromise = await fetch(`${path}/similar/avg.json?daysAgo=${days}`);
    await handleResponse(similarClansPromise, commit, "setSimilarClansAvg");
    await handleResponse(promise, commit, "setPreviousData");
    await handleResponse(clanStatsPromise, commit, "setClanStats");
    commit("stopLoading");
    dispatch("fetchSavedClanStats");
  }
};

// getters are functions
const getters = {
  header({ clan }) {
    if (clan.length > 0) {
      return clan[0].map(column => ({
        label: column,
        field: camelCase(column),
        numeric: !isNonNumericColumns(camelCase(column))
      }));
    } else {
      return [];
    }
  },
  path({ tag }) {
    return `/clan/${tag.replace("#", "")}`;
  },
  tableData(state, getters) {
    if (state.clan.length === 0) {
      return [];
    }
    const data = convertToMap(getters.header, state.clan.slice(1));
    const previousData = convertToMap(getters.header, state.previousData.slice(1));
    const previousByTag = keyBy(previousData, "tag");

    return data.map(row => {
      const previousRow = previousByTag[row.tag];
      return reduce(
        row,
        (map, value, column) => {
          const delta = previousRow && !isNonNumericColumns(column) ? value - previousRow[column] : 0;
          map[column] = { value, delta };
          if (column == "tag") {
            map["id"] = value;
          }
          return map;
        },
        {}
      );
    });
  }
};

const convertToMap = (header, matrix) => {
  return matrix.map(row => {
    return reduce(
      row,
      (map, value, columnIndex) => {
        map[header[columnIndex].field] = value;
        return map;
      },
      {}
    );
  });
};

const isNonNumericColumns = key => key == "tag" || key == "name";

export default new Vuex.Store({
  strict: true,
  state,
  getters,
  actions,
  mutations
});
