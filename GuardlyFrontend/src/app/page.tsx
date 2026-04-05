'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useGuardly } from '@/hooks/useGuardly';
import type { ChatMessage } from '@/types/guardly';

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoadingResponse, setIsLoadingResponse] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const guardly = useGuardly();

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!inputValue.trim()) {
      return;
    }

    // Add user message
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoadingResponse(true);

    try {
      // Simulate assistant response (in real app, this would call your LLM)
      // For demo purposes, we'll create a simple response
      const assistantOutput = generateDemoResponse(inputValue);

      // Validate the response
      const validationResult = await guardly.validate(
        inputValue,
        assistantOutput,
        inputValue // In real app, this would be retrieved from context/docs
      );

      const assistantMessage: ChatMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: assistantOutput,
        validation: validationResult
          ? {
              decision: validationResult.decision,
              risk_score: validationResult.risk_score,
              confidence: validationResult.confidence,
              evidence: validationResult.evidence,
              latency_ms: validationResult.latency_ms,
            }
          : undefined,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setTimeout(scrollToBottom, 100);
    } catch (error) {
      console.error('Error processing message:', error);
      const errorMessage: ChatMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Sorry, there was an error processing your message.',
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoadingResponse(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white shadow-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold">G</span>
            </div>
            <h1 className="text-xl font-bold text-gray-900">Guardly Chat</h1>
            <span className="ml-2 text-sm text-gray-500">Hallucination Detection</span>
          </div>
          <Link
            href="/settings"
            className="text-gray-600 hover:text-gray-900 text-sm font-medium transition-colors"
          >
            ⚙️ Settings
          </Link>
        </div>
      </header>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto bg-gray-50">
        <div className="max-w-4xl mx-auto">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <div className="bg-blue-100 rounded-full w-16 h-16 flex items-center justify-center mb-4">
                <span className="text-3xl">💬</span>
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                Start a Conversation
              </h2>
              <p className="text-gray-600 max-w-md">
                Chat with an AI assistant. All responses are validated in real-time
                for accuracy and hallucinations.
              </p>
            </div>
          ) : (
            <div className="py-4 px-4">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`mb-4 flex ${
                    message.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`max-w-2xl rounded-lg px-4 py-3 ${
                      message.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white text-gray-900 border border-gray-200'
                    }`}
                  >
                    <p className="text-sm break-words">{message.content}</p>

                    {/* Validation Badge */}
                    {message.validation && (
                      <div className="mt-2 pt-2 border-t border-gray-200">
                        <ValidationBadge validation={message.validation} />
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isLoadingResponse && (
                <div className="flex justify-start mb-4">
                  <div className="bg-white text-gray-900 border border-gray-200 rounded-lg px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                        <div
                          className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                          style={{ animationDelay: '0.1s' }}
                        ></div>
                        <div
                          className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                          style={{ animationDelay: '0.2s' }}
                        ></div>
                      </div>
                      <span className="text-sm text-gray-600 ml-2">
                        Thinking and validating...
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 bg-white">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Type your message..."
              disabled={isLoadingResponse}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
            />
            <button
              type="submit"
              disabled={isLoadingResponse || !inputValue.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
            >
              Send
            </button>
          </form>
          <p className="text-xs text-gray-500 mt-2">
            All responses are validated for accuracy in real-time.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * ValidationBadge Component
 * Displays validation status with visual indicators
 */
function ValidationBadge({
  validation,
}: {
  validation: NonNullable<ChatMessage['validation']>;
}) {
  const decisionConfig = {
    allow: {
      icon: '✓',
      bgColor: 'bg-green-50',
      textColor: 'text-green-700',
      label: 'Validation Passed',
    },
    block: {
      icon: '✗',
      bgColor: 'bg-red-50',
      textColor: 'text-red-700',
      label: 'Hallucination Detected',
    },
    regenerate: {
      icon: '↻',
      bgColor: 'bg-yellow-50',
      textColor: 'text-yellow-700',
      label: 'Needs Regeneration',
    },
    abstain: {
      icon: '?',
      bgColor: 'bg-gray-100',
      textColor: 'text-gray-700',
      label: 'Unable to Validate',
    },
  };

  const config = decisionConfig[validation.decision];
  const riskPercentage = Math.round(validation.risk_score * 100);
  const confidentPercentage = Math.round(validation.confidence * 100);

  return (
    <div className={`text-xs ${config.bgColor} ${config.textColor} rounded p-2`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="font-bold text-base">{config.icon}</span>
        <span className="font-semibold">{config.label}</span>
      </div>

      <div className="space-y-1 text-xs">
        {/* Risk Score Bar */}
        <div className="flex items-center gap-2">
          <span className="w-12">Risk:</span>
          <div className="flex-1 bg-white bg-opacity-50 rounded h-1.5 overflow-hidden">
            <div
              className={`h-full transition-all ${
                validation.risk_score > 0.7
                  ? 'bg-red-500'
                  : validation.risk_score > 0.4
                    ? 'bg-yellow-500'
                    : 'bg-green-500'
              }`}
              style={{ width: `${riskPercentage}%` }}
            />
          </div>
          <span className="w-8 text-right">{riskPercentage}%</span>
        </div>

        {/* Confidence Bar */}
        <div className="flex items-center gap-2">
          <span className="w-12">Conf:</span>
          <div className="flex-1 bg-white bg-opacity-50 rounded h-1.5 overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${confidentPercentage}%` }}
            />
          </div>
          <span className="w-8 text-right">{confidentPercentage}%</span>
        </div>

        {/* Evidence */}
        {validation.evidence && (
          <div className="mt-2 pt-1 border-t border-current border-opacity-20">
            <p className="text-opacity-80">
              <strong>Evidence:</strong> {validation.evidence}
            </p>
          </div>
        )}

        {/* Latency */}
        {validation.latency_ms && (
          <p className="text-opacity-70 mt-1">
            ⏱️ Validated in {validation.latency_ms}ms
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Demo Response Generator
 * In a real app, this would call your LLM backend
 */
function generateDemoResponse(prompt: string): string {
  const responses: { [key: string]: string } = {
    hello: 'Hello! I\'m here to help you with any questions.',
    paris:
      'Paris is the capital of France, known for its art, fashion, and iconic landmarks like the Eiffel Tower.',
    python:
      'Python is a high-level, interpreted programming language known for its simplicity and readability.',
    default:
      'That\'s an interesting question. I\'ll do my best to provide you with an accurate answer.',
  };

  const lowerPrompt = prompt.toLowerCase();
  for (const key in responses) {
    if (lowerPrompt.includes(key)) {
      return responses[key];
    }
  }

  return responses.default;
}
