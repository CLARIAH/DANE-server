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
      allJobs: [],
      searchList: "",
      filteredList: [],
      bulkActions: ['Retry', 'Delete'],
      bulkAction: null,
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
          this.allJobs = data['jobs'];
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
      this.errored = false;
      this.refresh();
    },
    deleteJob: function(idx) {
      const index = this.allJobs.indexOf(idx);
      if (index > -1) {
        this.$delete(this.allJobs, index);
      }
    },
    doBulkAction: function() {
      if (this.bulkAction !== null && this.filteredList.length > 0) {
        vm.$refs.confirm.open(this.bulkAction, 'Are you sure you want to perform this bulk action on all jobs found?', 
        { color: 'warning' }).then((confirm) => {
          if (confirm) {
            switch (this.bulkAction) {
              case 'Retry':
                action = 'retry';
                break;
              case 'Delete':
                action = 'delete';
                break;
              default:
                action = null;
            }
            if (action !== null) {
              this.filteredList.forEach((value, index) => {
                fetch(new URL(`job/${value}/${action}`, Config.API).href) 
                  .then((resp) => {
                    if (!resp.ok) {
                      throw Error(resp.statusText, resp.status);
                    }
                  })
                .catch(error => {
                  if (error.fileName == 404) {
                    //console.log(`BULK ACTION: Job ${value} not found, skipping`);
                    return;
                  }
                  this.attempts++;
                  if (this.attempts < 5) {
                    setTimeout(this.load, (500 * Math.pow(2, this.attempts)));
                  } else {
                    this.errored = true;
                    throw error;
                  }
                })
              })
            }
          }
        })
      }
    }
  },
  computed: {
    jobsList: function() {
      let jl = [];
      if (this.filteredList.length > 0) {
        jl = this.filteredList;
      } else {
        jl = this.allJobs;
      }
      this.pages = Math.ceil(jl.length / this.perPage);
      if (this.page > this.pages) {
        this.page = 1;
      }
      return jl.slice(this.perPage * (this.page-1), 
              this.perPage * this.page);
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
      let eq = true;
      if (fl.length == this.filteredList.length) {
        eq = fl.every((n, i) => {
          return n == this.filteredList[i];
        });
      } else {
        eq = false;
      }
      if (!eq) {
        this.panels = [];
      }
      this.filteredList = fl;
    }, 500),
    page: function () {
      this.panels = [];
    },
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
    refreshJob: function() {
      this.job = {};
      this.load();
    },
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
          setTimeout(this.retry, 500 * Math.pow(2, this.attempts));
        } else {
          throw error;
        }
      })
    },
    deleteJob: function() {
      vm.$refs.confirm.open('Delete job', 'Are you sure you want to delete this job?', 
        { color: 'warning' }).then((confirm) => {
          if (confirm) {
            fetch(new URL(`job/${this.idx}/delete`, Config.API).href) 
              .then((resp) => {
                if (!resp.ok) {
                  throw Error(resp.statusText, resp.status);
                }
                this.job = {};
                this.$emit('deletedjob')
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
  created: function() {
      if (this.task == 'Task') {
        this.task_details = this.tasks['Task'];
      }
    },
  computed: {
    task: function () {
      return Object.keys(this.tasks)[0];
    }
  },
  methods: {
    forceRetry: function(task_id) {
      fetch(new URL(`task/${task_id}/forceretry`, Config.API).href) 
      .then((resp) => {
        if (!resp.ok) {
          throw Error(resp.statusText, resp.status);
        }
        return resp.json() 
      })
      .then(data => {
        this.attempts = 0;
        this.$emit('refresh');
      })
      .catch(error => {
        this.attempts++;
        if (this.attempts < 5) {
          setTimeout(this.forceRetry, 
            500 * Math.pow(2, this.attempts),
            task_id);
        } else {
          throw error;
        }
      })
    },
    resetState: function(task_id) {
      fetch(new URL(`task/${task_id}/reset`, Config.API).href) 
      .then((resp) => {
        if (!resp.ok) {
          throw Error(resp.statusText, resp.status);
        }
        return resp.json() 
      })
      .then(data => {
        this.attempts = 0;
        this.$emit('refresh');
      })
      .catch(error => {
        this.attempts++;
        if (this.attempts < 5) {
          setTimeout(this.forceRetry, 
            500 * Math.pow(2, this.attempts),
            task_id);
        } else {
          throw error;
        }
      })
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
      source_id: '',
      source_url: '',
      tasks: ''
    }),
  methods: {
    newjob : function() {
      fetch(new URL('job', Config.API).href, {
        method: 'post',
        headers: {
          'Accept': 'application/json, text/plain, */*',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 'source_url': this.source_url,
          'source_id': this.source_id, 
          'tasks': JSON.parse(this.tasks)})
      })
      .then((resp) => {
        if (!resp.ok) {
          throw Error(resp.statusText, resp.status);
        }
        return resp.json() 
      })
      .then(res => {
        this.dialog = false; 
        this.$emit('refresh')
      }).catch(error => {
        alert(error);
      })
    }
  }
})

// https://gist.github.com/eolant/ba0f8a5c9135d1a146e1db575276177d
Vue.component('confirm', {
  template: '#confirm',
  data: () => ({
    dialog: false,
    resolve: null,
    reject: null,
    message: null,
    title: null,
    options: {
      color: 'primary',
      width: 290,
      zIndex: 200
    }
  }),
  methods: {
    open(title, message, options) {
      this.dialog = true
      this.title = title
      this.message = message
      this.options = Object.assign(this.options, options)
      return new Promise((resolve, reject) => {
        this.resolve = resolve
        this.reject = reject
      })
    },
    agree() {
      this.resolve(true)
      this.dialog = false
    },
    cancel() {
      this.resolve(false)
      this.dialog = false
    }
  }
});

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
