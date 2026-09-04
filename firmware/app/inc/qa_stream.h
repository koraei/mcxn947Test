#ifndef QA_STREAM_H_
#define QA_STREAM_H_

#ifndef APP_QA_STREAM
#define APP_QA_STREAM 0
#endif

#if APP_QA_STREAM
void qa_stream_service_start(void);
#else
static inline void qa_stream_service_start(void)
{
}
#endif

#endif /* QA_STREAM_H_ */
