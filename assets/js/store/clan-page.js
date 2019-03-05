import Vue from "vue";
import Vuex from "vuex";
import camelCase from "lodash/camelCase";
import reduce from "lodash/reduce";
import keyBy from "lodash/keyBy";
import { event } from "../ga";
import store from "store/dist/store.modern";

import { apolloClient } from "../client";
import { gql } from "apollo-boost";

Vue.use(Vuex);

const state = {
  tag: null,
  loading: true,
  clan: { recentData: window.__CLAN__, historicData: [] },
  lastUpdated: new Date(window.__LAST_UPDATED__) || null,
  playersStatus: {},
  days: 7,
  similarClansAvg: {},
  savedClanStats: {},
  daysSpan: 7,
  sortField: "value",
  apiError: null
};

const mutations = {
  setTag(state, tag) {
    state.tag = tag;
  },
  setData(state, data) {
    state.clan = data.clan;
    state.lastUpdated = new Date();
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
  if (response.status === 200) {
    const data = await response.json();
    commit(success, data);
    return data;
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
  async fetchClanData({ commit, dispatch, state: { tag, daysSpan } }) {
    dispatch("fetchSimilarClansStats");
    dispatch("fetchSavedClanStats");
    const { data } = await apolloClient.query({
      query: gql`
        query GetClan($tag: String!, $daysSpan: Int!, $refresh: Boolean = false) {
          clan(tag: $tag, refresh: $refresh) {
            name
            clanPoints
            members
            recentData: playerMatrix
            historicData: playerMatrix(days: $daysSpan)
            delta(days: $daysSpan) {
              avgDeGrab
              avgElixirGrab
              avgGoldGrab
            }
          }
        }
      `,
      variables: {
        tag,
        daysSpan
      }
    });
    commit("stopLoading");
    commit("setData", data);
  },
  async fetchSimilarClansStats({ commit, getters: { path }, state: { days } }) {
    const similarClansPromise = fetch(`${path}/similar/avg.json?daySpan=${days}`);
    handleResponse(similarClansPromise, commit, "setSimilarClansAvg");
  },
  async fetchSavedClanStats({ commit, state: { tag, days } }) {
    const savedTag = store.get("lastTag");
    if (savedTag && savedTag !== tag) {
      console.log(`Found saved tag value [${savedTag}].`);
      const savedClanStatsPromise = fetch(`/clan/${savedTag.replace("#", "")}/stats.json?daySpan=${days}`);
      handleResponse(savedClanStatsPromise, commit, "setSavedClanStats", false);
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
    dispatch("fetchSavedClanStats");
    dispatch("fetchSimilarClansStats");
    commit("startLoading");
    const promise = fetch(`${path}.json?daysAgo=${days}`);
    const clanStatsPromise = fetch(`${path}/stats.json?daysAgo=${days}`);
    await handleResponse(promise, commit, "setPreviousData");
    await handleResponse(clanStatsPromise, commit, "setClanStats");
    commit("stopLoading");
  }
};

const getters = {
  header({ clan }) {
    if (clan.recentData) {
      return clan.recentData[0].map(column => ({
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
  tableData({ clan }, getters) {
    if (!clan.recentData) {
      return [];
    }
    const data = convertToMap(getters.header, clan.recentData.slice(1));
    const previousData = convertToMap(getters.header, clan.historicData.slice(1));
    const previousByTag = keyBy(previousData, "tag");

    return data.map(row => {
      const previousRow = previousByTag[row.tag];
      return reduce(
        row,
        (map, value, column) => {
          const delta = previousRow && !isNonNumericColumns(column) ? value - previousRow[column] : 0;
          map[column] = { value, delta };
          if (column === "tag") {
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
