package server

import (
	"testing"
	"time"
)

func TestExtendExpiryFromNowWhenExpired(t *testing.T) {
	now := time.Date(2026, 2, 18, 10, 0, 0, 0, time.UTC)
	expired := now.Add(-24 * time.Hour)
	newExpire := extendExpiry(&expired, 7, now)
	want := now.Add(7 * 24 * time.Hour)
	if !newExpire.Equal(want) {
		t.Fatalf("expected %v, got %v", want, newExpire)
	}
}

func TestExtendExpiryFromCurrentWhenActive(t *testing.T) {
	now := time.Date(2026, 2, 18, 10, 0, 0, 0, time.UTC)
	current := now.Add(48 * time.Hour)
	newExpire := extendExpiry(&current, 30, now)
	want := current.Add(30 * 24 * time.Hour)
	if !newExpire.Equal(want) {
		t.Fatalf("expected %v, got %v", want, newExpire)
	}
}
