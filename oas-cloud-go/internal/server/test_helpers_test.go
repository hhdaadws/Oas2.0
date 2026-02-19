package server

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
	"time"

	"oas-cloud-go/internal/auth"
	"oas-cloud-go/internal/config"
	"oas-cloud-go/internal/models"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

type inMemoryStore struct {
	mu            sync.Mutex
	agentSessions map[string]uint
	jobLeases     map[string]leaseRecord
	scheduleSlots map[string]time.Time
}

type leaseRecord struct {
	nodeID   string
	expireAt time.Time
}

func newInMemoryStore() *inMemoryStore {
	return &inMemoryStore{
		agentSessions: map[string]uint{},
		jobLeases:     map[string]leaseRecord{},
		scheduleSlots: map[string]time.Time{},
	}
}

func (s *inMemoryStore) Close() error { return nil }

func (s *inMemoryStore) Ping(ctx context.Context) error { return nil }

func (s *inMemoryStore) SaveAgentSession(ctx context.Context, token string, managerID uint, nodeID string, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.agentSessions[token] = managerID
	return nil
}

func (s *inMemoryStore) ValidateAgentSession(ctx context.Context, token string, managerID uint) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	value, ok := s.agentSessions[token]
	return ok && value == managerID, nil
}

func (s *inMemoryStore) leaseKey(managerID uint, jobID uint) string {
	return strconv.FormatUint(uint64(managerID), 10) + ":" + strconv.FormatUint(uint64(jobID), 10)
}

func (s *inMemoryStore) AcquireJobLease(ctx context.Context, managerID uint, jobID uint, nodeID string, ttl time.Duration) (bool, error) {
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	key := s.leaseKey(managerID, jobID)
	now := time.Now().UTC()
	s.mu.Lock()
	defer s.mu.Unlock()
	if record, ok := s.jobLeases[key]; ok && record.expireAt.After(now) {
		return false, nil
	}
	s.jobLeases[key] = leaseRecord{nodeID: nodeID, expireAt: now.Add(ttl)}
	return true, nil
}

func (s *inMemoryStore) IsJobLeaseOwner(ctx context.Context, managerID uint, jobID uint, nodeID string) (bool, error) {
	key := s.leaseKey(managerID, jobID)
	now := time.Now().UTC()
	s.mu.Lock()
	defer s.mu.Unlock()
	record, ok := s.jobLeases[key]
	if !ok || !record.expireAt.After(now) {
		return false, nil
	}
	return record.nodeID == nodeID, nil
}

func (s *inMemoryStore) RefreshJobLease(ctx context.Context, managerID uint, jobID uint, nodeID string, ttl time.Duration) (bool, error) {
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	key := s.leaseKey(managerID, jobID)
	now := time.Now().UTC()
	s.mu.Lock()
	defer s.mu.Unlock()
	record, ok := s.jobLeases[key]
	if !ok || !record.expireAt.After(now) || record.nodeID != nodeID {
		return false, nil
	}
	record.expireAt = now.Add(ttl)
	s.jobLeases[key] = record
	return true, nil
}

func (s *inMemoryStore) ReleaseJobLease(ctx context.Context, managerID uint, jobID uint, nodeID string) error {
	key := s.leaseKey(managerID, jobID)
	s.mu.Lock()
	defer s.mu.Unlock()
	record, ok := s.jobLeases[key]
	if !ok || record.nodeID != nodeID {
		return nil
	}
	delete(s.jobLeases, key)
	return nil
}

func (s *inMemoryStore) ClearJobLease(ctx context.Context, managerID uint, jobID uint) error {
	key := s.leaseKey(managerID, jobID)
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.jobLeases, key)
	return nil
}

func (s *inMemoryStore) AcquireScheduleSlot(
	ctx context.Context,
	managerID uint,
	userID uint,
	taskType string,
	slot string,
	ttl time.Duration,
) (bool, error) {
	if ttl <= 0 {
		ttl = 60 * time.Second
	}
	key := strconv.FormatUint(uint64(managerID), 10) + ":" + strconv.FormatUint(uint64(userID), 10) + ":" + taskType + ":" + slot
	now := time.Now().UTC()
	s.mu.Lock()
	defer s.mu.Unlock()
	expireAt, ok := s.scheduleSlots[key]
	if ok && expireAt.After(now) {
		return false, nil
	}
	s.scheduleSlots[key] = now.Add(ttl)
	return true, nil
}

func setupTestServer(t *testing.T) (*Server, *gorm.DB) {
	t.Helper()
	db, err := gorm.Open(sqlite.Open("file::memory:?cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite failed: %v", err)
	}
	if err := models.AutoMigrate(db); err != nil {
		t.Fatalf("auto migrate failed: %v", err)
	}

	cfg := config.Config{
		Addr:               ":0",
		DatabaseURL:        "sqlite",
		RedisAddr:          "memory",
		RedisPassword:      "",
		RedisDB:            0,
		RedisKeyPrefix:     "test",
		JWTSecret:          "test-secret",
		JWTTTL:             24 * time.Hour,
		AgentJWTTTL:        12 * time.Hour,
		UserTokenTTL:       24 * time.Hour,
		DefaultLeaseSecond: 60,
		MaxPollLimit:       20,
		SchedulerEnabled:   false,
		SchedulerInterval:  5 * time.Second,
		SchedulerScanLimit: 100,
		SchedulerSlotTTL:   90 * time.Second,
	}
	server := New(cfg, db, newInMemoryStore())
	return server, db
}

func doJSONRequest(t *testing.T, handler http.Handler, method string, path string, body any, token string) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	var err error
	if body != nil {
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body failed: %v", err)
		}
	}
	req := httptest.NewRequest(method, path, bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

func createActiveManager(t *testing.T, db *gorm.DB, username string, password string) models.Manager {
	t.Helper()
	hash, err := auth.HashPassword(password)
	if err != nil {
		t.Fatalf("hash password failed: %v", err)
	}
	expireAt := time.Now().UTC().Add(30 * 24 * time.Hour)
	manager := models.Manager{
		Username:     username,
		PasswordHash: hash,
		Status:       models.ManagerStatusActive,
		ExpiresAt:    &expireAt,
		CreatedAt:    time.Now().UTC(),
		UpdatedAt:    time.Now().UTC(),
	}
	if err := db.Create(&manager).Error; err != nil {
		t.Fatalf("create manager failed: %v", err)
	}
	return manager
}

func createSuperAdmin(t *testing.T, db *gorm.DB, username string, password string) models.SuperAdmin {
	t.Helper()
	hash, err := auth.HashPassword(password)
	if err != nil {
		t.Fatalf("hash password failed: %v", err)
	}
	admin := models.SuperAdmin{
		Username:     username,
		PasswordHash: hash,
		CreatedAt:    time.Now().UTC(),
		UpdatedAt:    time.Now().UTC(),
	}
	if err := db.Create(&admin).Error; err != nil {
		t.Fatalf("create super admin failed: %v", err)
	}
	return admin
}

func ptrTime(value time.Time) *time.Time {
	return &value
}

func itoa(id uint) string {
	return strconv.FormatUint(uint64(id), 10)
}

func extractTokenFromBody(t *testing.T, raw []byte) string {
	t.Helper()
	payload := map[string]any{}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("unmarshal response failed: %v", err)
	}
	token, _ := payload["token"].(string)
	return token
}

func decodeBodyMap(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	payload := map[string]any{}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("unmarshal response failed: %v", err)
	}
	return payload
}
