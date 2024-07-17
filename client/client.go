package client

import (
	"fmt"
	"math"
	"math/rand"
	"net"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"go.uber.org/zap"

	"allen.gg/bufferbloater/stats"
)

type WorkloadStage struct {
	RPS      uint
	Duration time.Duration
}

type Target struct {
	Address string
	Port    uint
}

type RetryConfig struct {
	Count       int
	Factor      int
	Base        time.Duration
	MaxInterval time.Duration
}

type Config struct {
	Workload       []WorkloadStage
	RequestTimeout time.Duration
	Retry          RetryConfig
	TargetServer   Target
}

type Client struct {
	config     Config
	log        *zap.SugaredLogger
	statsMgr   *stats.StatsMgr
	httpClient *http.Client

	// Tenant ID.
	tid uint
}

var requestCounter uint64

func (c *Client) generateRequestID() string {
	return fmt.Sprintf("%d-%d", c.tid, atomic.AddUint64(&requestCounter, 1))
}

func NewClient(tenantId uint, config Config, logger *zap.SugaredLogger, sm *stats.StatsMgr) *Client {
	c := Client{
		tid:      tenantId,
		config:   config,
		log:      logger,
		statsMgr: sm,
		httpClient: &http.Client{
			Timeout:   config.RequestTimeout,
			Transport: &http.Transport{},
		},
	}

	logger.Infow("done creating client",
		"config", c.config)

	return &c
}

func (c *Client) sendWorkloadRequest(maxRetry int, numRetries int, requestID string) {
	remainingRetry := maxRetry - numRetries
	if remainingRetry < 0 {
		return
	}

	defer c.statsMgr.Incr("client.rq.total.count", c.tid)
	targetString := fmt.Sprintf("http://%s:%d", c.config.TargetServer.Address, c.config.TargetServer.Port)

	rqStart := time.Now()
	defer c.statsMgr.DirectMeasurement("client.rq.total_hist", rqStart, 1.0, c.tid)

	req, err := http.NewRequest("GET", targetString, nil)
	if err != nil {
		c.log.Errorw("error creating request", "error", err, "client", c.tid)
		return
	}

	// Tells the server to close the connection when done.
	req.Close = true

	resp, err := c.httpClient.Do(req)
	rqEnd := time.Now()
	latency := time.Since(rqStart)

	// Handle timeouts and report error otherwise.
	if err != nil {
		if err, ok := err.(net.Error); ok && err.Timeout() {
			c.log.Warnw("request timed outt", "client", c.tid)

			// Directly measuring timeouts because we only care about the point-in-time
			// the request that timed out was sent.
			c.statsMgr.DirectMeasurement("client.rq.timeout_origin", rqStart, 1.0, c.tid)
			c.statsMgr.DirectMeasurement("client.rq.timeout", rqEnd, 1.0, c.tid)
			c.statsMgr.Incr("client.rq.timeout.count", c.tid)
		} else {
			// c.log.Errorw("request error", "error", err, "client", c.tid)
			c.statsMgr.Incr("client.rq.non_timeout_error.count", c.tid)
		}
		c.statsMgr.Incr("client.rq.failure.count", c.tid)
		// Retry logic
		// c.log.Warnw("retry logic", "maxRetry", maxRetry,
		// 	"numRetries", numRetries,
		// 	"remainingRetry", remainingRetry,
		// 	"client", c.tid)
		if remainingRetry > 0 {
			// c.log.Warnw("Retry entry", "requestID", requestID, "client", c.tid)
			go func() {
				// Calculate backoff time for retry
				numRetries += 1
				waitTime := c.config.Retry.Base * time.Duration(math.Pow(float64(c.config.Retry.Factor), float64(numRetries-1)))
				jitter := 0.5
				jitterTime := time.Duration(rand.Float64() * jitter * float64(waitTime))
				waitTime += jitterTime
				waitTime = time.Duration(math.Min(float64(waitTime), float64(c.config.Retry.MaxInterval)))
				// c.log.Warnw("backoff start", "requestID", requestID, "num", numRetries, "waitTime", waitTime, "client", c.tid)
				time.Sleep(waitTime)
				c.log.Warnw("backoff done, send retry", "requestID", requestID, "numRetries", numRetries, "waitTime", waitTime)
				c.statsMgr.Incr("client.rq.retry.count", c.tid)
				c.sendWorkloadRequest(maxRetry, numRetries, requestID)
			}()
		}
		return
	}
	resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
		c.statsMgr.DirectMeasurement("client.rq.latency", rqStart, float64(latency.Seconds()), c.tid)
		c.statsMgr.DirectMeasurement("client.rq.success_hist", rqStart, 1.0, c.tid)
		c.statsMgr.Incr("client.rq.success.count", c.tid)
		return
	case http.StatusServiceUnavailable, http.StatusTooManyRequests:
		c.statsMgr.DirectMeasurement("client.rq.503", rqStart, 1.0, c.tid)
		c.statsMgr.Incr("client.rq.failure.count", c.tid)
	case http.StatusRequestTimeout, http.StatusGatewayTimeout:
		c.statsMgr.DirectMeasurement("client.rq.timeout_origin", rqStart, 1.0, c.tid)
		c.statsMgr.DirectMeasurement("client.rq.timeout", rqEnd, 1.0, c.tid)
	default:
		c.log.Fatalw("wtf is this", "status", resp.StatusCode, "resp", resp, "client", c.tid)
	}

	c.log.Fatalw("SHOULD NOT BE REACHED")
	os.Exit(1)

	// if remainingRetry > 0 {
	// 	numRetries += 1
	// 	c.statsMgr.Incr("client.rq.retry.count", c.tid)
	// 	go c.sendWorkloadRequest(maxRetry, numRetries)
	// }
}

func (c *Client) processWorkloadStage(ws WorkloadStage) {

	// Divide the requests/sec evenly into the duration of this stage. We can cast
	// an integral type to a time.Duration since time.Duration is an int64 behind
	// the scenes.
	requestSpacing := time.Second / time.Duration(ws.RPS)
	c.log.Infow("client workload stage started", "client", c.tid, "rps", ws.RPS, "duration", ws.Duration, "spacing", requestSpacing)
	ticker := time.NewTicker(requestSpacing)

	var wg sync.WaitGroup
	wg.Add(1)
	done := make(chan struct{})
	go func(wg *sync.WaitGroup) {
		defer wg.Done()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				numRetries := 0
				requestID := c.generateRequestID()
				c.statsMgr.Set("client.rps", float64(ws.RPS), c.tid)
				go c.sendWorkloadRequest(c.config.Retry.Count, numRetries, requestID)
			}
		}
	}(&wg)
	time.Sleep(ws.Duration)
	done <- struct{}{}
	wg.Wait()
}

func (c *Client) Start(wg *sync.WaitGroup) {
	defer wg.Done()

	for _, stage := range c.config.Workload {
		c.log.Infow("processing new client workload stage", "stage", stage, "client", c.tid)
		c.processWorkloadStage(stage)
	}

	c.log.Infow("client workload finished", "client", c.tid)
}
