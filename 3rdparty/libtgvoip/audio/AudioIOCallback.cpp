#include "AudioIOCallback.h"
#include "../VoIPController.h"
#include "../logging.h"

using namespace tgvoip;
using namespace tgvoip::audio;

#pragma mark - IO

AudioIOCallback::AudioIOCallback() {
    input  = new AudioInputCallback();
    output = new AudioOutputCallback();
}

AudioIOCallback::~AudioIOCallback() {
    // Ensure worker threads are asked to exit before objects are deleted
    Stop();
    delete input;
    delete output;
}

AudioInput* AudioIOCallback::GetInput() {
    return input;
}

AudioOutput* AudioIOCallback::GetOutput() {
    return output;
}

#pragma mark - Input

AudioInputCallback::AudioInputCallback() {
    running   = false;
    recording = false;
    thread = new Thread(std::bind(&AudioInputCallback::RunThread, this));
    thread->SetName("AudioInputCallback");
}

AudioInputCallback::~AudioInputCallback() {
    // Ensure thread exits and is joined once
    running   = false;
    recording = false;
    if (thread) {
        thread->Join();
        delete thread;
        thread = nullptr;
    }
}

void AudioInputCallback::Start() {
    if (!running) {
        running   = true;
        thread->Start();
    }
    recording = true;
}

// PATCH 3: AudioInputCallback::Stop

void AudioInputCallback::Stop(){
        if(!running)
                return;
        recording=false;
        running=false;    // make RunThread exit ASAP
        if(thread){
                thread->Join();
        }
}

void AudioInputCallback::SetDataCallback(std::function<void(int16_t*, size_t)> c) {
    dataCallback = std::move(c);
}

// PATCH 1: AudioInputCallback::RunThread

void AudioInputCallback::RunThread(){
        int16_t buf[960];
        while(running){
                // --- added to re-check and avoid blocking if stop was requested ---
                if (!running)
                        break;

                double t=VoIPController::GetCurrentTime();
                memset(buf, 0, sizeof(buf));
                if(dataCallback){
                        dataCallback(buf, 960);
                }
                InvokeCallback(reinterpret_cast<unsigned char*>(buf), 960*2);
                double sl=0.02-(VoIPController::GetCurrentTime()-t);
                if(sl>0){
                        // Sleep in small chunks and re-check 'running'
                        const double step = 0.005;
                        while(sl>0 && running){
                                Thread::Sleep(std::min(sl, step));
                                sl-=step;
                        }
                }
        }
}

#pragma mark - Output

AudioOutputCallback::AudioOutputCallback() {
    running = false;
    playing = false;
    thread = new Thread(std::bind(&AudioOutputCallback::RunThread, this));
    thread->SetName("AudioOutputCallback");
}

AudioOutputCallback::~AudioOutputCallback() {
    running = false;
    playing = false;
    if (thread) {
        thread->Join();
        delete thread;
        thread = nullptr;
    }
}

void AudioOutputCallback::Start() {
    if (!running) {
        running = true;
        thread->Start();
    }
    playing = true;
}

// PATCH 4: AudioOutputCallback::Stop

void AudioOutputCallback::Stop(){
        if(!running)
                return;
        playing=false;
        running=false;     // make RunThread exit ASAP
        if(thread){
                thread->Join();
        }
}

bool AudioOutputCallback::IsPlaying() {
    return playing;
}

void AudioOutputCallback::SetDataCallback(std::function<void(int16_t*, size_t)> c) {
    dataCallback = std::move(c);
}

// PATCH 2: AudioOutputCallback::RunThread

void AudioOutputCallback::RunThread(){
        int16_t buf[960];
        while(running){
                // --- added to re-check and avoid blocking if stop was requested ---
                if (!running)
                        break;

                double t=VoIPController::GetCurrentTime();
                memset(buf, 0, sizeof(buf));
                InvokeCallback(reinterpret_cast<unsigned char*>(buf), 960*2);
                if(dataCallback){
                        dataCallback(buf, 960);
                }
                double sl=0.02-(VoIPController::GetCurrentTime()-t);
                if(sl>0){
                        // Sleep in small chunks and re-check 'running'
                        const double step = 0.005;
                        while(sl>0 && running){
                                Thread::Sleep(std::min(sl, step));
                                sl-=step;
                        }
                }
        }
}
