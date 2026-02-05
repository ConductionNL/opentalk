import Vue from 'vue'
import App from './App.vue'

Vue.mixin({ methods: { t, n } })

const appElement = document.getElementById('opentalk')
if (appElement) {
	new Vue({
		el: appElement,
		render: h => h(App),
	})
}
