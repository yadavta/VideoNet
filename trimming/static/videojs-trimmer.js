// SOURCE: https://cdn.jsdelivr.net/gh/Teyuto/videojs-trimmer@main/src/videojs-trimmer.js
// SOURCE: https://github.com/Teyuto/videojs-trimmer/blob/509c78d2f4f3073d898342829991986d817ccc75/src/videojs-trimmer.js
(function(videojs) {
    const Plugin = videojs.getPlugin('plugin');
  
    class Trimmer extends Plugin {
      constructor(player, options) {
        super(player, options);
        this.player = player;
        this.startTime = 0;
        this.endTime = 0;
        this.originalDuration = 0;
  
        this.createTrimmer();
  
        this.player.on('loadedmetadata', () => {
          this.originalDuration = this.player.duration();
          this.endTime = this.originalDuration;
          this.updateTrimmer();
          // this.createTimeMarkers();
        });
  
        this.player.addClass('video-js-trimmer');

        this.bindEvents();

        return this
      }

      foo() {
        return "Hello World"
      }
  
      createTrimmer() {
        const progressControl = this.player.controlBar.progressControl.el();
  
        this.trimmerEl = document.createElement('div');
        this.trimmerEl.className = 'vjs-trimmer';
        progressControl.appendChild(this.trimmerEl);
  
        this.startHandle = document.createElement('div');
        this.startHandle.className = 'vjs-trimmer-handle start';
        progressControl.appendChild(this.startHandle);
  
        this.endHandle = document.createElement('div');
        this.endHandle.className = 'vjs-trimmer-handle end';
        progressControl.appendChild(this.endHandle);
  
        this.updateTrimmer();
      }
  
      bindEvents() {
        let isDraggingStart = false;
        let isDraggingEnd = false;
  
        const onMouseMove = (event) => {
          const progressControl = this.player.controlBar.progressControl.el();
          const rect = progressControl.getBoundingClientRect();
          const pos = (event.clientX - rect.left) / rect.width * this.originalDuration;
  
          if (isDraggingStart) {
            this.startTime = Math.min(Math.max(pos, 0), this.endTime);
          } else if (isDraggingEnd) {
            this.endTime = Math.max(Math.min(pos, this.originalDuration), this.startTime);
          }
  
          this.updateTrimmer();
          // this.player.trigger('trimmerchange', {
          //   startTime: this.startTime,
          //   endTime: this.endTime
          // });
        };
  
        const onMouseUp = () => {
          isDraggingStart = false;
          isDraggingEnd = false;
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          // this.player.currentTime(0);
        };
  
        this.startHandle.addEventListener('mousedown', () => {
          isDraggingStart = true;
          document.addEventListener('mousemove', onMouseMove);
          document.addEventListener('mouseup', onMouseUp);
        });
  
        this.endHandle.addEventListener('mousedown', () => {
          isDraggingEnd = true;
          document.addEventListener('mousemove', onMouseMove);
          document.addEventListener('mouseup', onMouseUp);
        });
      }
  
      updateTrimmer() {
        const progressControl = this.player.controlBar.progressControl.el();
        const startPos = (this.startTime / this.originalDuration) * 100;
        const endPos = (this.endTime / this.originalDuration) * 100;
  
        this.trimmerEl.style.left = `${startPos}%`;
        this.trimmerEl.style.width = `${endPos - startPos}%`;
  
        this.startHandle.style.left = `${startPos}%`;
        this.endHandle.style.left = `${endPos}%`;
  
        // this.player.offset({
        //   start: this.startTime,
        //   end: this.endTime
        // });
      }
  
      // createTimeMarkers() {
      //   const progressControl = this.player.controlBar.progressControl.el();
      //   const markerContainer = document.createElement('div');
      //   markerContainer.className = 'vjs-time-markers';
      //   progressControl.appendChild(markerContainer);
  
      //   const numMarkers = 20; // Numero di marker da visualizzare
      //   for (let i = 0; i <= numMarkers; i++) {
      //     const marker = document.createElement('div');
      //     marker.className = 'vjs-time-marker';
      //     const time = (i / numMarkers) * this.originalDuration;
      //     marker.style.left = `${(i / numMarkers) * 100}%`;
          
      //     const timeLabel = document.createElement('span');
      //     timeLabel.className = 'vjs-time-label';
      //     timeLabel.textContent = this.formatTime(time);
          
      //     marker.appendChild(timeLabel);
      //     markerContainer.appendChild(marker);
      //   }
      // }
  
      formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
      }
    }
  
    videojs.registerPlugin('trimmer', Trimmer);
  })(videojs);