/**
 * Bounded, one-shot Jinja renderer for Home Assistant Lovelace.
 *
 * Unlike render_template over the WebSocket API, POST /api/template is a
 * one-shot operation: it cannot leave a server-side RenderInfo subscription
 * behind.  Explicit entities are required so unrelated Home Assistant state
 * updates never cause a render.  Relevant bursts are trailing-edge debounced,
 * with a hard maximum wait, and requests are strictly serialized.
 */
const BUILD_ID = "v3-20260813.1";
const ELEMENT_NAME = "debounced-html-template-card-v3-20260813";
const DEBOUNCE_MS = 500;
const MAX_WAIT_MS = 5000;

class DebouncedHtmlTemplateCardV3 extends HTMLElement {
    constructor() {
        super();
        this._config = undefined;
        this._hass = undefined;
        this._entities = [];
        this._rootElement = undefined;

        this._epoch = 0;
        this._dirty = false;
        this._inFlight = undefined;
        this._debounceTimer = undefined;
        this._maxWaitTimer = undefined;

        this._cachedTemplate = undefined;
        this._cachedResult = undefined;
    }

    static get BUILD_ID() {
        return BUILD_ID;
    }

    static get DEBOUNCE_MS() {
        return DEBOUNCE_MS;
    }

    static get MAX_WAIT_MS() {
        return MAX_WAIT_MS;
    }

    set hass(hass) {
        const oldHass = this._hass;
        const connectionChanged = Boolean(
            oldHass && oldHass.connection !== hass?.connection,
        );
        this._hass = hass;

        if (!this._config || this._config.do_not_parse) {
            return;
        }

        if (connectionChanged) {
            // A response issued through the old HA connection must never paint
            // after a reconnect.  The request itself cannot be cancelled, so a
            // new epoch makes its response stale and queues one fresh render.
            this._invalidatePendingWork();
        }

        if (
            !oldHass
            || connectionChanged
            || this._config.always_update
            || this._trackedEntityChanged(oldHass, hass)
        ) {
            this._scheduleRender();
        }
    }

    setConfig(config) {
        this._validateConfig(config);

        // Invalidate before replacing the DOM.  An older REST response may
        // still resolve, but the epoch check below prevents a stale repaint.
        this._invalidatePendingWork();
        if (this._rootElement && this.contains(this._rootElement)) {
            this.removeChild(this._rootElement);
        }

        this._config = config;
        this._entities = Array.isArray(config.entities)
            ? [...new Set(config.entities)]
            : [];
        this._rootElement = config.picture_elements_mode
            ? document.createElement("div")
            : document.createElement("ha-card");
        if (!config.picture_elements_mode) {
            this._rootElement.style.padding = "16px";
        }
        this._ensureRootAttached();

        const template = this._templateContent(config);
        if (config.do_not_parse) {
            this.render(template);
            return;
        }

        // Lovelace can call setConfig again while rebuilding a view.  Repaint a
        // successful result for the identical template immediately so the card
        // does not flash blank while the bounded refresh is pending.
        if (
            this._cachedTemplate === template
            && this._cachedResult !== undefined
        ) {
            this.render(this._cachedResult);
        }

        if (this.isConnected && this._hass) {
            this._scheduleRender();
        }
    }

    connectedCallback() {
        this._ensureRootAttached();
        if (!this._config) {
            return;
        }
        if (this._config.do_not_parse) {
            this.render(this._templateContent(this._config));
        } else if (this._hass) {
            this._scheduleRender();
        }
    }

    disconnectedCallback() {
        // Fetch cannot be cancelled portably here.  Invalidating the epoch is
        // sufficient: the response is ignored and no follow-up is scheduled.
        this._invalidatePendingWork();
    }

    _validateConfig(config) {
        if (!config?.content) {
            throw new Error("You need to define 'content' in your configuration.");
        }
        if (config.do_not_parse) {
            return;
        }
        if (!Array.isArray(config.entities) || config.entities.length === 0) {
            throw new Error(
                "You need to define a non-empty explicit 'entities' list for server-rendered content.",
            );
        }
        if (config.entities.some((entityId) => typeof entityId !== "string" || !entityId)) {
            throw new Error("Every entry in 'entities' must be a non-empty entity ID string.");
        }
    }

    _trackedEntityChanged(oldHass, newHass) {
        return this._entities.some((entityId) => {
            const oldState = oldHass?.states?.[entityId];
            const newState = newHass?.states?.[entityId];
            return oldState !== newState
                || oldState?.attributes !== newState?.attributes;
        });
    }

    _templateContent(config = this._config) {
        let content = config.content;
        if (!config.ignore_line_breaks) {
            content = content.replace(/\r?\n|\r/g, "</br>");
        }
        return content;
    }

    _invalidatePendingWork() {
        ++this._epoch;
        this._dirty = false;
        this._clearRenderTimers();
    }

    _scheduleRender() {
        if (
            !this._config
            || this._config.do_not_parse
            || !this._hass
            || !this.isConnected
        ) {
            return;
        }

        this._dirty = true;
        if (this._inFlight) {
            // The completion path starts exactly one immediate follow-up using
            // the newest config and HA object.  No overlapping request is made.
            return;
        }

        if (this._debounceTimer !== undefined) {
            clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = setTimeout(() => {
            this._flushScheduledRender();
        }, DEBOUNCE_MS);

        if (this._maxWaitTimer === undefined) {
            this._maxWaitTimer = setTimeout(() => {
                this._flushScheduledRender();
            }, MAX_WAIT_MS);
        }
    }

    _flushScheduledRender() {
        this._clearRenderTimers();
        if (!this._dirty || this._inFlight) {
            return;
        }
        this._startRender();
    }

    _startRender() {
        if (
            this._inFlight
            || !this._dirty
            || !this._config
            || this._config.do_not_parse
            || !this._hass
            || !this.isConnected
        ) {
            return;
        }

        this._clearRenderTimers();
        this._dirty = false;
        const request = {
            epoch: this._epoch,
            hass: this._hass,
            template: this._templateContent(),
        };
        this._inFlight = request;

        let response;
        try {
            response = request.hass.callApi(
                "POST",
                "template",
                {template: request.template},
            );
        } catch (error) {
            response = Promise.reject(error);
        }

        request.promise = Promise.resolve(response)
            .then((result) => {
                if (
                    this._inFlight !== request
                    || request.epoch !== this._epoch
                    || !this.isConnected
                    || !this._config
                    || this._config.do_not_parse
                    || request.template !== this._templateContent()
                    || this._dirty
                ) {
                    return;
                }
                const rendered = result == null ? "" : String(result);
                this._cachedTemplate = request.template;
                this._cachedResult = rendered;
                this.render(rendered);
            })
            .catch((error) => {
                if (request.epoch === this._epoch && this.isConnected) {
                    console.error(
                        `debounced-html-template-card (${BUILD_ID}) render failed`,
                        error,
                    );
                }
            })
            .finally(() => {
                if (this._inFlight !== request) {
                    return;
                }
                this._inFlight = undefined;
                if (
                    this._dirty
                    && this._config
                    && !this._config.do_not_parse
                    && this._hass
                    && this.isConnected
                ) {
                    // Entity/config changes accumulated during the request are
                    // collapsed into one immediate, serialized follow-up.
                    this._startRender();
                }
            });
    }

    _clearRenderTimers() {
        if (this._debounceTimer !== undefined) {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = undefined;
        }
        if (this._maxWaitTimer !== undefined) {
            clearTimeout(this._maxWaitTimer);
            this._maxWaitTimer = undefined;
        }
    }

    _ensureRootAttached() {
        if (this._rootElement && !this.contains(this._rootElement)) {
            this.appendChild(this._rootElement);
        }
    }

    render(content) {
        let header = "";
        if (this._config.title) {
            header = `<div class="card-header" style="padding: 8px 0 16px 0;"><div class="name">${this._config.title}</div></div>`;
        }
        this._rootElement.innerHTML = this._config.picture_elements_mode
            ? content
            : `${header}<div>${content}</div>`;
    }

    getCardSize() {
        return 1;
    }
}

if (!customElements.get(ELEMENT_NAME)) {
    customElements.define(ELEMENT_NAME, DebouncedHtmlTemplateCardV3);
}
