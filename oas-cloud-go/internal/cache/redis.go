package cache

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	"oas-cloud-go/internal/auth"
	"oas-cloud-go/internal/config"

	"github.com/redis/go-redis/v9"
)

type RedisStore struct {
	client *redis.Client
	prefix string
}

type Store interface {
	Close() error
	Ping(ctx context.Context) error
	SaveAgentSession(ctx context.Context, token string, managerID uint, nodeID string, ttl time.Duration) error
	ValidateAgentSession(ctx context.Context, token string, managerID uint) (bool, error)
	AcquireJobLease(ctx context.Context, managerID uint, jobID uint, nodeID string, ttl time.Duration) (bool, error)
	IsJobLeaseOwner(ctx context.Context, managerID uint, jobID uint, nodeID string) (bool, error)
	RefreshJobLease(ctx context.Context, managerID uint, jobID uint, nodeID string, ttl time.Duration) (bool, error)
	ReleaseJobLease(ctx context.Context, managerID uint, jobID uint, nodeID string) error
	ClearJobLease(ctx context.Context, managerID uint, jobID uint) error
	AcquireScheduleSlot(
		ctx context.Context,
		managerID uint,
		userID uint,
		taskType string,
		slot string,
		ttl time.Duration,
	) (bool, error)
}

func NewRedisStore(cfg config.Config) (*RedisStore, error) {
	client := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisAddr,
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, err
	}
	prefix := strings.TrimSuffix(cfg.RedisKeyPrefix, ":")
	if prefix == "" {
		prefix = "oas:cloud"
	}
	return &RedisStore{
		client: client,
		prefix: prefix,
	}, nil
}

func (r *RedisStore) Close() error {
	return r.client.Close()
}

func (r *RedisStore) Ping(ctx context.Context) error {
	return r.client.Ping(ctx).Err()
}

func (r *RedisStore) key(parts ...string) string {
	all := make([]string, 0, len(parts)+1)
	all = append(all, r.prefix)
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		all = append(all, part)
	}
	return strings.Join(all, ":")
}

func (r *RedisStore) SaveAgentSession(
	ctx context.Context,
	token string,
	managerID uint,
	nodeID string,
	ttl time.Duration,
) error {
	if ttl <= 0 {
		ttl = time.Hour
	}
	key := r.key("agent", "session", auth.HashToken(token))
	fields := map[string]any{
		"manager_id": managerID,
		"node_id":    nodeID,
		"updated_at": time.Now().UTC().Format(time.RFC3339),
	}
	pipe := r.client.TxPipeline()
	pipe.HSet(ctx, key, fields)
	pipe.Expire(ctx, key, ttl)
	_, err := pipe.Exec(ctx)
	return err
}

func (r *RedisStore) ValidateAgentSession(
	ctx context.Context,
	token string,
	managerID uint,
) (bool, error) {
	key := r.key("agent", "session", auth.HashToken(token))
	stored, err := r.client.HGet(ctx, key, "manager_id").Result()
	if err == redis.Nil {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	id, err := strconv.ParseUint(stored, 10, 64)
	if err != nil {
		return false, fmt.Errorf("invalid redis manager_id: %w", err)
	}
	return uint(id) == managerID, nil
}

func (r *RedisStore) AcquireJobLease(
	ctx context.Context,
	managerID uint,
	jobID uint,
	nodeID string,
	ttl time.Duration,
) (bool, error) {
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	key := r.key("job", "lease", strconv.FormatUint(uint64(managerID), 10), strconv.FormatUint(uint64(jobID), 10))
	return r.client.SetNX(ctx, key, nodeID, ttl).Result()
}

func (r *RedisStore) IsJobLeaseOwner(
	ctx context.Context,
	managerID uint,
	jobID uint,
	nodeID string,
) (bool, error) {
	key := r.key("job", "lease", strconv.FormatUint(uint64(managerID), 10), strconv.FormatUint(uint64(jobID), 10))
	value, err := r.client.Get(ctx, key).Result()
	if err == redis.Nil {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return value == nodeID, nil
}

func (r *RedisStore) RefreshJobLease(
	ctx context.Context,
	managerID uint,
	jobID uint,
	nodeID string,
	ttl time.Duration,
) (bool, error) {
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	key := r.key("job", "lease", strconv.FormatUint(uint64(managerID), 10), strconv.FormatUint(uint64(jobID), 10))
	script := redis.NewScript(`
local current = redis.call("GET", KEYS[1])
if not current then
  return 0
end
if current ~= ARGV[1] then
  return 0
end
redis.call("PEXPIRE", KEYS[1], ARGV[2])
return 1
`)
	res, err := script.Run(ctx, r.client, []string{key}, nodeID, ttl.Milliseconds()).Int()
	if err != nil {
		return false, err
	}
	return res == 1, nil
}

func (r *RedisStore) ReleaseJobLease(
	ctx context.Context,
	managerID uint,
	jobID uint,
	nodeID string,
) error {
	key := r.key("job", "lease", strconv.FormatUint(uint64(managerID), 10), strconv.FormatUint(uint64(jobID), 10))
	script := redis.NewScript(`
local current = redis.call("GET", KEYS[1])
if not current then
  return 1
end
if current ~= ARGV[1] then
  return 0
end
redis.call("DEL", KEYS[1])
return 1
`)
	res, err := script.Run(ctx, r.client, []string{key}, nodeID).Int()
	if err != nil {
		return err
	}
	if res == 0 {
		return fmt.Errorf("lease owner mismatch")
	}
	return nil
}

func (r *RedisStore) ClearJobLease(
	ctx context.Context,
	managerID uint,
	jobID uint,
) error {
	key := r.key("job", "lease", strconv.FormatUint(uint64(managerID), 10), strconv.FormatUint(uint64(jobID), 10))
	return r.client.Del(ctx, key).Err()
}

func (r *RedisStore) AcquireScheduleSlot(
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
	key := r.key(
		"scheduler",
		"slot",
		strconv.FormatUint(uint64(managerID), 10),
		strconv.FormatUint(uint64(userID), 10),
		taskType,
		slot,
	)
	return r.client.SetNX(ctx, key, "1", ttl).Result()
}
