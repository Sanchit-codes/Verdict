'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getGuardedClient } from '@/lib/guardly-client';
import type { GuardlySettings, HealthStatus } from '@/types/guardly';

const DEFAULT_SETTINGS: GuardlySettings = {
  apiEndpoint: 'http://localhost:5500/api',
  validationPolicy: 'default',
  validationEnabled: true,
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<GuardlySettings>(DEFAULT_SETTINGS);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [hasChanged, setHasChanged] = useState(false);

  // Load settings from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('guardly_settings');
    if (saved) {
      try {
        setSettings(JSON.parse(saved));
      } catch (e) {
        console.error('Failed to parse saved settings:', e);
      }
    }
  }, []);

  const handleApiEndpointChange = (newEndpoint: string) => {
    setSettings((prev) => ({
      ...prev,
      apiEndpoint: newEndpoint,
    }));
    setHasChanged(true);
    setSaveMessage(null);
  };

  const handlePolicyChange = (newPolicy: 'default' | 'rag_strict' | 'chatbot') => {
    setSettings((prev) => ({
      ...prev,
      validationPolicy: newPolicy,
    }));
    setHasChanged(true);
    setSaveMessage(null);
  };

  const handleToggleValidation = () => {
    setSettings((prev) => ({
      ...prev,
      validationEnabled: !prev.validationEnabled,
    }));
    setHasChanged(true);
    setSaveMessage(null);
  };

  const handleSaveSettings = () => {
    try {
      localStorage.setItem('guardly_settings', JSON.stringify(settings));
      const client = getGuardedClient();
      client.setApiBaseUrl(settings.apiEndpoint);
      setHasChanged(false);
      setSaveMessage('Settings saved successfully!');
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (error) {
      setSaveMessage('Failed to save settings. Please try again.');
      console.error('Error saving settings:', error);
    }
  };

  const handleHealthCheck = async () => {
    setIsTesting(true);
    try {
      const client = getGuardedClient();
      const health = await client.getHealth();
      setHealthStatus(health);
    } catch (error) {
      console.error('Health check failed:', error);
      setHealthStatus({
        status: 'unhealthy',
        timestamp: new Date().toISOString(),
        message: 'Failed to connect to backend',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const getHealthBadgeColor = (status?: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-100 text-green-800';
      case 'degraded':
        return 'bg-yellow-100 text-yellow-800';
      case 'unhealthy':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getHealthIcon = (status?: string) => {
    switch (status) {
      case 'healthy':
        return '✓';
      case 'degraded':
        return '⚠';
      case 'unhealthy':
        return '✗';
      default:
        return '?';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white shadow-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold">G</span>
            </div>
            <h1 className="text-xl font-bold text-gray-900">Guardly Settings</h1>
          </div>
          <Link
            href="/"
            className="text-gray-600 hover:text-gray-900 text-sm font-medium transition-colors"
          >
            ← Back to Chat
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Save Message */}
        {saveMessage && (
          <div
            className={`mb-4 p-4 rounded-lg ${
              saveMessage.includes('success')
                ? 'bg-green-100 text-green-800'
                : 'bg-red-100 text-red-800'
            }`}
          >
            {saveMessage}
          </div>
        )}

        {/* API Endpoint Section */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <span>🔗</span> API Configuration
          </h2>

          <div className="space-y-4">
            <div>
              <label htmlFor="apiEndpoint" className="block text-sm font-medium text-gray-700 mb-2">
                API Endpoint
              </label>
              <input
                type="url"
                id="apiEndpoint"
                value={settings.apiEndpoint}
                onChange={(e) => handleApiEndpointChange(e.target.value)}
                placeholder="http://localhost:5500/api"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="mt-2 text-sm text-gray-600">
                The URL where the Guardly validation backend is running. Default is
                localhost:5500/api.
              </p>
            </div>

            {/* Health Check */}
            <div>
              <button
                onClick={handleHealthCheck}
                disabled={isTesting}
                className="w-full px-4 py-2 bg-blue-100 text-blue-700 hover:bg-blue-200 disabled:bg-gray-100 disabled:text-gray-500 rounded-lg font-medium transition-colors"
              >
                {isTesting ? 'Testing Connection...' : 'Test Connection'}
              </button>

              {healthStatus && (
                <div className="mt-3 p-3 rounded-lg bg-gray-50 border border-gray-200">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={`inline-block px-3 py-1 rounded font-medium text-sm ${getHealthBadgeColor(
                        healthStatus.status
                      )}`}
                    >
                      {getHealthIcon(healthStatus.status)}{' '}
                      {healthStatus.status?.charAt(0).toUpperCase() +
                        healthStatus.status?.slice(1)}
                    </span>
                  </div>
                  {healthStatus.message && (
                    <p className="text-sm text-gray-600">{healthStatus.message}</p>
                  )}
                  {healthStatus.version && (
                    <p className="text-xs text-gray-500 mt-1">
                      Version: {healthStatus.version}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Validation Policy Section */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <span>⚙️</span> Validation Policy
          </h2>

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Select Validation Policy
              </label>

              {[
                {
                  id: 'default',
                  name: 'Default',
                  description: 'Balanced policy for general-purpose applications',
                },
                {
                  id: 'rag_strict',
                  name: 'RAG Strict',
                  description: 'High-risk policy for RAG systems (healthcare, finance)',
                },
                {
                  id: 'chatbot',
                  name: 'Chatbot',
                  description: 'Low-latency policy optimized for chatbots',
                },
              ].map((policy) => (
                <label
                  key={policy.id}
                  className="flex items-start p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 mb-2"
                >
                  <input
                    type="radio"
                    name="policy"
                    value={policy.id}
                    checked={settings.validationPolicy === policy.id}
                    onChange={(e) =>
                      handlePolicyChange(
                        e.target.value as 'default' | 'rag_strict' | 'chatbot'
                      )
                    }
                    className="mt-1 w-4 h-4 text-blue-600 rounded"
                  />
                  <div className="ml-3">
                    <p className="font-medium text-gray-900">{policy.name}</p>
                    <p className="text-sm text-gray-600">{policy.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Validation Toggle Section */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <span>✓</span> Validation Status
          </h2>

          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-gray-900">
                {settings.validationEnabled ? 'Enabled' : 'Disabled'}
              </p>
              <p className="text-sm text-gray-600">
                Responses will{' '}
                {settings.validationEnabled ? 'be' : 'not be'} validated for
                hallucinations
              </p>
            </div>

            <button
              onClick={handleToggleValidation}
              className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors ${
                settings.validationEnabled ? 'bg-green-600' : 'bg-gray-300'
              }`}
            >
              <span
                className={`inline-block h-6 w-6 transform rounded-full bg-white transition-transform ${
                  settings.validationEnabled ? 'translate-x-7' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex gap-3">
          <button
            onClick={handleSaveSettings}
            disabled={!hasChanged}
            className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed font-medium transition-colors"
          >
            Save Settings
          </button>

          <button
            onClick={() => {
              const saved = localStorage.getItem('guardly_settings');
              if (saved) {
                setSettings(JSON.parse(saved));
              } else {
                setSettings(DEFAULT_SETTINGS);
              }
              setHasChanged(false);
            }}
            disabled={!hasChanged}
            className="flex-1 px-6 py-3 bg-gray-200 text-gray-900 rounded-lg hover:bg-gray-300 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed font-medium transition-colors"
          >
            Reset
          </button>
        </div>

        {/* Info Section */}
        <div className="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h3 className="font-semibold text-blue-900 mb-2">💡 About Guardly</h3>
          <p className="text-sm text-blue-800">
            Guardly prevents AI hallucinations by validating all generated text
            before it reaches users. Settings are stored locally and persisted
            across sessions.
          </p>
        </div>
      </main>
    </div>
  );
}
