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

Vue.component('dane-document', {
  template: '#dane-document',
  props: ['doc_id'],
  data: function() {
    return {
      doc: {},
      errored: false,
      attempts: 0,
      dialog: false,
      loading: true,
      tasks: []
    }
  }, 
  created: function() {
      this.load();
    },
  watch: {
    doc_id: function(n, o) { if (n != o) this.load(); }
  },
  methods: {
      load: function() {
        if (this.doc_id != null) { 
          fetch(new URL(`document/${this.doc_id}`, Config.API).href) 
          .then((resp) => {
            if (!resp.ok) {
              this.errored = true;
              this.loading = false;
              throw Error(resp.statusText);
            }
            return resp.json() 
          })
          .then(data => {
            this.doc = data;
            this.loading = false;
            this.loadTasks();
            })
          .catch(error => {
            // because network errors are type errors..
            if (error.name == 'TypeError') {
              this.loading = false;
              this.errored = true;
            }
            throw error;
          });
        }
      },
      loadTasks: function() {
        fetch(new URL(`document/${this.doc._id}/tasks`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            this.errored = true;
            this.loading = false;
            throw Error(resp.statusText);
          }
          return resp.json() 
        })
        .then(data => {
          this.tasks = data;
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
      deleteDoc: function() {
      vm.$refs.confirm.open('Delete document', 'Are you sure you want to delete this document?', 
        { color: 'warning' }).then((confirm) => {
          if (confirm) {
            fetch(new URL(`document/${this.doc_id}`, Config.API).href, {
              'method': 'DELETE' 
            }) 
              .then((resp) => {
                if (!resp.ok) {
                  throw Error(resp.statusText, resp.status);
                }
                this.doc = {};
                this.tasks = [];
                this.$emit('deleteddoc');
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
    },
      newVal: function(task) {
      this.tasks.find((o, i) => {
        if (o._id == task._id) {
          if (task.state == "000") {
              this.$delete(this.tasks, i);
          } else {
            Vue.set(this.tasks, i, {});
            setTimeout(() => { // add delay so we see change
              Vue.set(this.tasks, i, task);
            }, 10);
          }
          return true;
        }
      });
     }
   }
})

Vue.component('dane-doc-search', {
  template: '#dane-doc-search',
   data: function() {
      return {
        results: [],
        headers: [
          { 'text': 'id', value: '_id' },
          { 'text': 'target', value: 'target.id' },
          { 'text': 'type', value: 'target.type' },
          { 'text': 'creator', value: 'creator.id' }
        ]
      }
    },
    methods: {
      clickRow: function(value) {
        vm.switchDoc(value._id);
      },
      search: function() {
        this.$refs.searchbar.search();
      }
    }
})

Vue.component('dane-doc-searchbar', {
  template: '#dane-doc-searchbar',
  data: function() {
      return {
        target: "",
        creator: "",
        docs: []
      }
    }, 
  created: function() {
    this.search();
  },
  methods: {
    search: function() {
      let t = ((this.target.length > 0) ? this.target : '*');
      let c = ((this.creator.length > 0) ? this.creator : '*');
      fetch(new URL(`search/document?target_id=${t}&creator_id=${c}`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            this.docs = [];
            this.$emit('input', this.docs);
            throw Error(resp.statusText);
          }
          return resp.json() 
        })
        .then(data => {
            this.docs = data['hits'];
            this.$emit('input', this.docs);
          })
        .catch(error => {
          // because network errors are type errors..
          if (error.name == 'TypeError') {
            this.docs = [];
            this.$emit('input', this.docs);
          }
          throw error;
        });
     }
  }
})

Vue.component('dane-tasklist', {
  template: '#dane-tasklist',
  props: {
    value: Array,
    in_doc: {
      type: String,
      default: "true"
    }
  },
   data: function() {
      return {
        errored: false,
      }
    },
  methods: {
      goDoc: function(id) {
        fetch(new URL(`task/${id}/document`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            throw Error(resp.statusText, resp.status);
          }
          return resp.json() 
        })
        .then(data => {
          vm.switchDoc(data['_id']);
        })
      },
      retryTask: function(id) {
        this.doAction(id, 'retry');
      },
      resetTask: function(id) {
        this.doAction(id, 'reset');
      },
      forceRetryTask: function(id) {
        this.doAction(id, 'forceretry');
      },
      deleteTask: function(id) {
        vm.$refs.confirm.open('Delete task', 'Are you sure you want to delete this task?', 
        { color: 'warning' }).then((confirm) => {
          if (confirm) {
            fetch(new URL(`task/${id}`, Config.API).href, {
              method: 'DELETE' 
            }) 
            .then((resp) => {
              if (!resp.ok) {
                throw Error(resp.statusText, resp.status);
              }
              // create artificial object to show deletion
                this.$emit('newval', {'_id': id, 
                  'state': "000",
                  'key': "DELETED",
                  'msg': "Task deleted"});
            })
          }
        })
      },
      doAction: function(id, action) {
        fetch(new URL(`task/${id}/${action}`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            throw Error(resp.statusText, resp.status);
          }
          return resp.json() 
        })
        .then(data => {
          this.$emit('newval', data);
        })
      },
      colour: function(s) {
        if ([200].includes(parseInt(s))) {
          return 'green';
        } else if ([102, 201, 205].includes(parseInt(s))) {
          return 'yellow';
        } else {
          return 'red';
        }
      },
      goTask: function(key) {
        vm.switchWorker(key);
      }
   }
})

Vue.component('dane-newdoc', {
  template: '#dane-newdoc',
  data: () => ({
      dialog: false,
      types: ["Dataset", "Image", "Video", "Sound", "Text"],
      agents: ["Organization", "Human", "Software"],
      target_id: '',
      target_url: '',
      target_type: '',
      creator_id: '',
      creator_type: '',
      state: ''
    }),
  methods: {
    newjob : function() {
      if (this.target_id.length > 0 && this.target_url.length > 0 
        && this.creator_id.length > 0 && this.target_type.length > 0
      && this.creator_type.length > 0) {
        try {
        fetch(new URL('document/', Config.API).href, {
          method: 'post',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 'target': {
              'id': this.target_id,
              'url': this.target_url,
              'type': this.target_type 
            },
            'creator': {
                'id': this.creator_id,
                'type': this.creator_type 
            }
          })
        })
        .then((resp) => {
          if (!resp.ok) {
            throw Error(resp.statusText, resp.status);
          }
          return resp.json() 
        })
        .then(res => {
          this.dialog = false; 
          this.$emit('refresh', res)
        }).catch(error => {
          alert(error);
        })
        } catch(error) {
          this.state = 'Error: ' + error.message;
          console.error(error);
        }
      } else {
        this.state = 'Please specify all fields.';
      }
    }
  }
})

Vue.component('dane-workers', {
  template: '#dane-workers',
   data: function() {
      return {
        results: [],
        headers: [
          { 'text': 'Name', value: 'name' },
          { 'text': 'Active workers', value: 'active_workers' },
          { 'text': 'In queue', value: 'in_queue' }
        ]
      }
    },
  created: function() {
      this.load();
    },
  methods: {
      clickRow: function(value) {
        vm.switchWorker(value.name);
      },
      load: function() {
        fetch(new URL(`workers`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            this.errored = true;
            this.loading = false;
            throw Error(resp.statusText);
          }
          return resp.json() 
        })
        .then(data => {
          this.results = data;
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
   }
})

Vue.component('dane-newtask', {
  template: '#dane-newtask',
  props: ['value'],
  data: () => ({
      dialog: false,
      task_key: '',
      priority: 1,
      state: ''
    }),
  methods: {
    assign: function() {
      if (this.task_key.length > 0) {
        try {
        fetch(new URL('task/', Config.API).href, {
          method: 'post',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 'document_id': this.value,
            'task': {
                'key': this.task_key,
                'priority': this.priority 
            }
          })
        })
        .then((resp) => {
          if (!resp.ok) {
            throw Error(resp.statusText, resp.status);
          }
          return resp.json() 
        })
        .then(res => {
          this.dialog = false; 
          this.$emit('newtask', res)
        }).catch(error => {
          alert(error);
        })
        } catch(error) {
          this.state = 'Error: ' + error.message;
          console.error(error);
        }
      } else {
        this.state = 'Please specify all fields.';
      }
    }
  }
})

Vue.component('dane-worker-details', {
  template: '#dane-worker-details',
  props: ['taskkey'],
   data: function() {
      return {
        tasks: [],
        taskcount: 0,
        resetstates: [400, 403, 404, 422, 500],
        state: 500,
        resetres: "",
        errored: false
      }
    },
  created: function() {
      this.load();
    },
  watch: {
    taskkey: function(n, o) { if (n != o) this.load(); }
  },
  methods: {
      load: function() {
        fetch(new URL(`workers/${this.taskkey}`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            this.errored = true;
            throw Error(resp.statusText);
          }
          return resp.json() 
        })
        .then(data => {
          this.tasks = data['tasks'];
          this.taskcount = data['total'];
          })
        .catch(error => {
          // because network errors are type errors..
          if (error.name == 'TypeError') {
            this.errored = true;
          }
          throw error;
        });
      },
    newVal: function(task) {
      this.tasks.find((o, i) => {
        if (o._id == task._id) {
          if (task.state == "000") {
              this.$delete(this.tasks, i);
          } else {
            Vue.set(this.tasks, i, {});
            setTimeout(() => { // add delay so we see change
              Vue.set(this.tasks, i, task);
            }, 10);
          }
          return true;
        }
      });
     },
    massreset: function() {
      fetch(new URL(`workers/${this.taskkey}/reset/${this.state}`, Config.API).href) 
        .then((resp) => {
          if (!resp.ok) {
            this.errored = true;
            throw Error(resp.statusText);
          }
          return resp.json() 
        })
        .then(data => {
            if (data['error'].length > 0) {
              this.resetres = data['error'];
            } else {
              this.resetres = data['total'].toString() + " tasks reset.";
              this.load()
            }
          })
        .catch(error => {
          // because network errors are type errors..
          if (error.name == 'TypeError') {
            this.errored = true;
          }
          throw error;
        });
    }
   }
})

Vue.component('api-form', {
  template: '#api-form',
  data: () => ({
      new_api: Config.API,
      dialog: false
  }),
  methods: {
    open: function() {
      this.dialog = true;  
    },
    update: function() {
      Config.API = this.new_api;
      this.dialog = false;
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
  }),
  data: () => ({
    tab: "overview",
    worker: null,
    doc: null
  }),
  methods:  {
    goOverview() {
      this.doc = null;
      this.tab = 'overview';
    },
    switchDoc(id) {
      this.doc = id;
      this.tab = 'document';
    },
    switchWorker(key) {
      this.worker = key;
      this.tab = 'worker';
    },
  }
})
