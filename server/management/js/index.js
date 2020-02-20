function debounce (fn, delay) {
  var timeoutID = null
  return function () {
    clearTimeout(timeoutID)
    var args = arguments
    var that = this
    timeoutID = setTimeout(function () {
      fn.apply(that, args)
    }, delay)
  }
}

Vue.component('dane-jobslist', {
  template: '#dane-jobslist',
  data: function() {
    return {
      _jobsList: [],
      searchList: [],
      filteredList: [],
      panels: [],
      loading: true,
      errored: false,
      api: Config.API,
      perPage: 10,
      pages: 1,
      page: 1
    }
  }, 

  created: function() {
      this.load();
    },
  methods: {
      load: function() {
        fetch(new URL('job/inprogress', Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            throw Error(resp.statusText);
          }
          return resp.json() 
        })
        .then(data => {
          this._jobsList = data['jobs'];
          this.loading = false;
          })
        .catch(error => {
          // because network errors are type errors..
          if (error.name == 'TypeError') {
            this.loading = false;
            this.errored = true;
          }
          throw error;
        });
      },
    refresh: function() {
      this.loading = true;
      this.load();
    },
    updateAPI: function(api) {
      Config.API = api;
      this.errored= false;
      this.refresh();
    }
  },
  watch: {
    searchList: debounce(function () {
      fl = []
      if (this.searchList.length > 0) {
        fl = this.searchList.replace(/([,\s]+$)/g, '').split(',').map(
          job => parseInt(job)
        )
        .filter(
          job => Number.isInteger(job) && job > 0
        ).sort(function (a, b) {  return a - b;  });
        fl = Array.from(new Set(fl));
      } 
      this.filteredList = fl;
    }, 500),
    page: function () {
      this.panels = [];
    }
  },
  computed: {
    jobsList: function() {
      let jl = [];
      if (this.filteredList.length > 0) {
        jl = this.filteredList;
      } else {
        jl = this._jobsList;
      }
      this.pages = Math.ceil(jl.length / this.perPage);
      if (this.page > this.pages) {
        this.page = 1;
      }
      return jl.slice(this.perPage * (this.page-1), 
        this.perPage * this.page);
    }
  }
})
        
Vue.component('dane-job-panel', {
  props: ['idx'],
  template: '#dane-job-panel'
})

Vue.component('dane-job', {
  props: ['idx'],
  template: '#dane-job',

  data: function() {
    return {
      job: {},
      attempts: 0,
      errored: false
    }
  },

  mounted: function() {
    this.load()
  },

  methods: {
    load: function() {
      if (Object.keys(this.job).length > 0) { return; }
      fetch(new URL(`job/${this.idx}`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            throw Error(resp.statusText, resp.status);
          }
          return resp.json() 
        })
       .then(data => {
         this.job = data;
         this.attempts = 0;
       })
      .catch(error => {
        if (error.fileName == 404) {
          this.errored = true;
          throw error
        }
        this.attempts++;
        if (this.attempts < 5) {
          setTimeout(this.load, (500 * Math.pow(2, this.attempts)));
        } else {
          this.errored = true;
          throw error;
        }
      })
    },
    retry: function() {
      this.job = {};

      fetch(new URL(`job/${this.idx}/retry`, Config.API).href) 
      .then((resp) => {
        if (!resp.ok) {
          throw Error(resp.statusText, resp.status);
        }
        return resp.json() 
      })
      .then(data => {
         this.job = data;
         this.attempts = 0;
      })
      .catch(error => {
        this.attempts++;
        if (this.attempts < 5) {
          setTimeout(this.load, 500 * Math.pow(2, this.attempts));
        } else {
          throw error;
        }
      })
    }
  }
})
        
Vue.component('dane-taskcontainer', {
  props: ['tasks'],
  template: '#dane-taskcontainer',
  data: function() {
    return {
        task_details: {}
    }
  },
  computed: {
    task: function () {
      return Object.keys(this.tasks)[0];
    }
  }
})
        
Vue.component('dane-task', {
  props: ['task'],
  template: '#dane-task',
  computed: {
    task_key: function () {
      if (this.task.hasOwnProperty('Task')) {
        return this.task['Task'].task_key;
      } else {
        return Object.keys(this.task)[0];
      }
    }
  },
  methods: {
    details: function() {
      if (this.$el.className.includes('v-slide-item--active')) {
          this.$emit('details', {})
      } else if (this.task.hasOwnProperty('Task')) {
          this.$emit('details', this.task['Task'])
      } else {
          this.$emit('details', this.task)
      }
    }
  }
})

Vue.component('api-form', {
  props: ['value'],
  template: '#api-form',
  data: function() {
    return {
        new_api: Config.API
    }
  },
})

Vue.component('dane-newjob', {
  template: '#dane-newjob',
  data: () => ({
      dialog: false,
    }),
  methods: {
    newjob : function() {
      alert('pressed');
    }
  }
})

var loc = window.location;
var baseUrl = loc.protocol + "//" + loc.hostname + (loc.port? ":"+loc.port : "") + "/"

var Config = {
  API: new URL('/DANE/', baseUrl).href
}

var vm = new Vue({
  el: '#app',
  vuetify: new Vuetify({
    theme: {
    themes: {
      light: {
          primary: "#ff5722",
          secondary: "#ffc107",
          accent: "#e91e63",
          error: "#f44336",
          warning: "#3f51b5",
          info: "#009688",
          success: "#8bc34a"
      },
    },
    }
  })
})
