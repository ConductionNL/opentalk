<template>
	<div id="opentalk-app">
		<NcEmptyContent
			:name="t('opentalk', 'OpenTalk')"
			:description="t('opentalk', 'Video conferencing integration for Nextcloud')">
			<template #icon>
				<VideoIcon :size="64" />
			</template>
		</NcEmptyContent>
	</div>
</template>

<script>
import { NcEmptyContent } from '@nextcloud/vue'
import VideoIcon from 'vue-material-design-icons/Video.vue'

export default {
	name: 'App',
	components: {
		NcEmptyContent,
		VideoIcon,
	},
}
</script>
