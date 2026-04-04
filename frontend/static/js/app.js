// HallucinationGuard Testing Frontend JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('validation-form');
    const validateBtn = document.getElementById('validate-btn');
    const resultsSection = document.getElementById('results-section');
    const resultsContent = document.getElementById('results-content');
    const loadExampleBtn = document.getElementById('load-example-btn');
    const exampleModal = document.getElementById('example-modal');
    const modalClose = document.querySelector('.modal-close');
    const examplesList = document.getElementById('examples-list');

    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = new FormData(form);
        const data = {
            prompt: formData.get('prompt'),
            output: formData.get('output'),
            context: formData.get('context'),
            policy: formData.get('policy'),
            domain: formData.get('domain')
        };

        // Show loading state
        validateBtn.disabled = true;
        validateBtn.innerHTML = '<div class="loading"></div> Validating...';

        try {
            const response = await fetch('/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();
            
            if (response.ok) {
                displayResults(result);
            } else {
                displayError(result.error || 'Validation failed');
            }
        } catch (error) {
            displayError('Network error: ' + error.message);
        } finally {
            // Reset button
            validateBtn.disabled = false;
            validateBtn.innerHTML = '<i class="fas fa-search"></i> Validate';
        }
    });

    // Load examples
    loadExampleBtn.addEventListener('click', async function() {
        try {
            const response = await fetch('/examples');
            const examples = await response.json();
            
            examplesList.innerHTML = '';
            examples.forEach(example => {
                const exampleItem = document.createElement('div');
                exampleItem.className = 'example-item';
                exampleItem.innerHTML = `
                    <h4>${example.name}</h4>
                    <p>${example.description}</p>
                    <div class="example-prompt">"${example.prompt.substring(0, 100)}${example.prompt.length > 100 ? '...' : ''}"</div>
                `;
                exampleItem.addEventListener('click', () => loadExample(example));
                examplesList.appendChild(exampleItem);
            });
            
            exampleModal.style.display = 'flex';
        } catch (error) {
            console.error('Failed to load examples:', error);
        }
    });

    // Modal close
    modalClose.addEventListener('click', () => {
        exampleModal.style.display = 'none';
    });

    // Close modal when clicking outside
    exampleModal.addEventListener('click', (e) => {
        if (e.target === exampleModal) {
            exampleModal.style.display = 'none';
        }
    });

    function loadExample(example) {
        document.getElementById('prompt').value = example.prompt;
        document.getElementById('output').value = example.output || '';
        document.getElementById('context').value = example.context || '';
        exampleModal.style.display = 'none';
    }

    function displayResults(result) {
        const statusIndicator = document.getElementById('overall-status');
        
        // Set status indicator
        statusIndicator.className = 'status-indicator';
        statusIndicator.classList.add(`status-${result.decision.toLowerCase()}`);
        statusIndicator.textContent = result.decision.toUpperCase();

        // Build results HTML
        let html = `
            <div class="result-card ${result.decision === 'block' ? 'blocked' : ''}">
                <h3><i class="fas fa-chart-bar"></i> Overall Decision</h3>
                <div class="metric">
                    <strong>Decision:</strong>
                    <span class="decision-${result.decision.toLowerCase()}">${result.decision.toUpperCase()}</span>
                </div>
                <div class="metric">
                    <strong>Risk Score:</strong>
                    <span>${result.risk_score.toFixed(3)}</span>
                </div>
                <div class="metric">
                    <strong>Latency:</strong>
                    <span>${result.latency_ms}ms</span>
                </div>
                <div class="metric">
                    <strong>Prompt Injection Risk:</strong>
                    <span>${result.prompt_injection_risk.toFixed(3)}</span>
                </div>
                ${result.evidence ? `
                    <div class="evidence">
                        <strong>Evidence:</strong><br>
                        ${result.evidence}
                    </div>
                ` : ''}
                ${result.suggested_fix ? `
                    <div class="evidence">
                        <strong>Suggested Fix:</strong><br>
                        ${result.suggested_fix}
                    </div>
                ` : ''}
            </div>
        `;

        // Add prompt security metadata
        if (result.prompt_security_metadata && Object.keys(result.prompt_security_metadata).length > 0) {
            html += `
                <div class="result-card">
                    <h3><i class="fas fa-shield-alt"></i> Prompt Security Analysis (Tier 0.5)</h3>
                    ${Object.entries(result.prompt_security_metadata).map(([key, value]) => `
                        <div class="metric">
                            <strong>${formatKey(key)}:</strong>
                            <span>${formatValue(value)}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        // Add tier results
        if (result.tier_results && result.tier_results.length > 0) {
            html += '<div class="tier-results">';
            html += '<h3><i class="fas fa-layer-group"></i> Detailed Tier Results</h3>';
            
            result.tier_results.forEach(tier => {
                html += `
                    <div class="tier-result ${tier.passed ? 'passed' : 'failed'}">
                        <div class="tier-header">
                            <span class="tier-name">${tier.validator_name} (Tier ${tier.tier})</span>
                            <span class="tier-score">${tier.score.toFixed(3)} (${tier.passed ? 'PASS' : 'FAIL'})</span>
                        </div>
                        ${tier.evidence ? `<div class="evidence">${tier.evidence}</div>` : ''}
                        <div class="metric" style="margin-top: 0.5rem;">
                            <strong>Latency:</strong>
                            <span>${tier.latency_ms}ms</span>
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
        }

        resultsContent.innerHTML = html;
        resultsSection.style.display = 'block';
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }

    function displayError(error) {
        const statusIndicator = document.getElementById('overall-status');
        statusIndicator.className = 'status-indicator status-block';
        statusIndicator.textContent = 'ERROR';

        resultsContent.innerHTML = `
            <div class="result-card blocked">
                <h3><i class="fas fa-exclamation-triangle"></i> Validation Error</h3>
                <div class="evidence">
                    <strong>Error:</strong><br>
                    ${error}
                </div>
            </div>
        `;
        resultsSection.style.display = 'block';
    }

    function formatKey(key) {
        return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    function formatValue(value) {
        if (typeof value === 'boolean') {
            return value ? 'Yes' : 'No';
        }
        if (Array.isArray(value)) {
            return value.length > 0 ? value.join(', ') : 'None';
        }
        if (typeof value === 'object' && value !== null) {
            return JSON.stringify(value, null, 2);
        }
        return String(value);
    }
});
