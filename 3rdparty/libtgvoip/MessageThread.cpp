//
// Created by Grishka on 17.06.2018.
//

#include <assert.h>
#include <time.h>
#include <math.h>
#include <float.h>
#include <stdint.h>

#ifndef _WIN32
#include <sys/time.h>
#endif

#include "MessageThread.h"
#include "VoIPController.h"
#include "logging.h"

using namespace tgvoip;

MessageThread::MessageThread() : Thread(std::bind(&MessageThread::Run, this)){

	SetName("MessageThread");

#ifdef _WIN32
#if !defined(WINAPI_FAMILY) || WINAPI_FAMILY!=WINAPI_FAMILY_PHONE_APP
	event=CreateEvent(NULL, false, false, NULL);
#else
	event=CreateEventEx(NULL, NULL, 0, EVENT_ALL_ACCESS);
#endif
#else
	pthread_cond_init(&cond, NULL);
#endif
}

MessageThread::~MessageThread(){
	Stop();
#ifdef _WIN32
	CloseHandle(event);
#else
	pthread_cond_destroy(&cond);
#endif
}

void MessageThread::HardStop(){
    queueMutex.Lock();
    running = false;
    hardStopped.store(true, std::memory_order_release);
    queue.clear();  // drop all pending messages
#ifndef _WIN32
    pthread_cond_broadcast(&cond);
#else
    SetEvent(event);
#endif
    queueMutex.Unlock();
}

void MessageThread::Stop(){
        queueMutex.Lock();
        running=false;
        queue.clear();                      // <--- NEW: drop all pending messages
#ifndef _WIN32
        pthread_cond_broadcast(&cond);
#else
        SetEvent(event);
#endif
        queueMutex.Unlock();
}

void MessageThread::Run(){
        queueMutex.Lock();
        while(running){
                double currentTime=VoIPController::GetCurrentTime();
                double waitTimeout=queue.empty() ? DBL_MAX : (queue[0].deliverAt-currentTime);
                if(waitTimeout>0.0){
#ifndef _WIN32
                        if(waitTimeout!=DBL_MAX){
                                struct timeval now;
                                struct timespec timeout;
                                gettimeofday(&now, NULL);
                                waitTimeout+=now.tv_sec;
                                waitTimeout+=(now.tv_usec/1000000.0);
                                timeout.tv_sec=(time_t)(floor(waitTimeout));
                                timeout.tv_nsec=(long)((waitTimeout-floor(waitTimeout))*1000000000.0);
                                pthread_cond_timedwait(&cond, queueMutex.NativeHandle(), &timeout);
                        }else{
                                pthread_cond_wait(&cond, queueMutex.NativeHandle());
                        }
#else
                        queueMutex.Unlock();
                        DWORD actualWaitTimeout=waitTimeout==DBL_MAX ? INFINITE : ((DWORD)round(waitTimeout*1000.0));
                        WaitForSingleObject(event, actualWaitTimeout);
                        queueMutex.Lock();
#endif
                }

                if(!running){
                        break;
                }

                currentTime=VoIPController::GetCurrentTime();
                std::vector<Message> msgsToDeliverNow;
                for(std::vector<Message>::iterator m=queue.begin();m!=queue.end();){
                        if(m->deliverAt==0.0 || currentTime>=m->deliverAt){
                                msgsToDeliverNow.push_back(*m);
                                m=queue.erase(m);
                                continue;
                        }
                        ++m;
                }

                // NEW: if HardStop was requested, do NOT execute any callbacks
                if(hardStopped.load(std::memory_order_acquire)){
                        // just drop msgsToDeliverNow and exit
                        break;
                }

                for(Message& m:msgsToDeliverNow){
                        cancelCurrent=false;
                        if(m.deliverAt==0.0)
                                m.deliverAt=VoIPController::GetCurrentTime();
                        if(m.func!=nullptr){
                                m.func();
                        }
                        if(!cancelCurrent && m.interval>0.0){
                                m.deliverAt+=m.interval;
                                InsertMessageInternal(m);
                        }
                }

        }
        queueMutex.Unlock();
}

uint32_t MessageThread::Post(std::function<void()> func, double delay, double interval){
	assert(delay>=0);
	//LOGI("MessageThread post [function] delay %f", delay);
	if(!IsCurrent()){
		queueMutex.Lock();
	}
	double currentTime=VoIPController::GetCurrentTime();
	Message m{lastMessageID++, delay==0.0 ? 0.0 : (currentTime+delay), interval, func};
	InsertMessageInternal(m);
	if(!IsCurrent()){
#ifdef _WIN32
		SetEvent(event);
#else
		pthread_cond_signal(&cond);
#endif
		queueMutex.Unlock();
	}
	return m.id;
}

void MessageThread::InsertMessageInternal(MessageThread::Message &m){
	if(queue.empty()){
		queue.push_back(m);
	}else{
		if(queue[0].deliverAt>m.deliverAt){
			queue.insert(queue.begin(), m);
		}else{
			std::vector<Message>::iterator insertAfter=queue.begin();
			for(; insertAfter!=queue.end(); ++insertAfter){
				std::vector<Message>::iterator next=std::next(insertAfter);
				if(next==queue.end() || (next->deliverAt>m.deliverAt && insertAfter->deliverAt<=m.deliverAt)){
					queue.insert(next, m);
					break;
				}
			}
		}
	}
}

void MessageThread::Cancel(uint32_t id){
	if(!IsCurrent()){
		queueMutex.Lock();
	}

	for(std::vector<Message>::iterator m=queue.begin();m!=queue.end();){
		if(m->id==id){
			m=queue.erase(m);
		}else{
			++m;
		}
	}

	if(!IsCurrent()){
		queueMutex.Unlock();
	}
}

void MessageThread::CancelSelf(){
	assert(IsCurrent());
	cancelCurrent=true;
}
