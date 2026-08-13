/**
 * Hotfix for PiotrMachowski/html-template-card v1.0.2.
 *
 * This preserves the card's public options and rendering while serializing the
 * complete asynchronous subscribe/unsubscribe lifecycle.  At most one server
 * render_template subscription can exist for this card instance.
 */
class HtmlTemplateCard extends HTMLElement {
    constructor() {
        super();
        this._config = undefined;
        this._hass = undefined;
        this._entities = undefined;
        this._rootElement = undefined;

        this._subscriptionGeneration = 0;
        this._desiredSubscription = undefined;
        this._activeSubscription = undefined;
        this._lifecycleQueue = Promise.resolve();
        this._reconcileScheduled = false;
    }

    static get properties() {
        return {
            _config: {},
            _hass: {},
        };
    }

    set hass(hass) {
        const oldHass = this._hass;
        const connectionChanged = Boolean(
            oldHass && oldHass.connection !== hass?.connection,
        );
        this._hass = hass;

        if (this._config && this._hass && !this._entities) {
            this.calculateEntites();
        }
        if (connectionChanged || this.shouldUpdate(oldHass)) {
            this.processAndRender();
        }
    }

    shouldUpdate(oldHass) {
        if (oldHass && this._entities && !this._config?.always_update) {
            return this._entities.some((entityId) => {
                const oldState = oldHass.states[entityId];
                const newState = this._hass.states[entityId];
                return oldState !== newState
                    || oldState?.attributes !== newState?.attributes;
            });
        }
        return true;
    }

    setConfig(config) {
        if (!config.content) {
            throw new Error("You need to define 'content' in your configuration.");
        }

        this._requestStop();
        if (this._rootElement && this.contains(this._rootElement)) {
            this.removeChild(this._rootElement);
        }

        this._config = config;
        this._entities = undefined;
        this._rootElement = config.picture_elements_mode
            ? document.createElement("div")
            : document.createElement("ha-card");
        if (!config.picture_elements_mode) {
            this._rootElement.style.padding = "16px";
        }

        if (this._hass) {
            this.calculateEntites();
        }
        this._ensureRootAttached();
        if (this.isConnected && this._hass) {
            this.processAndRender();
        }
    }

    connectedCallback() {
        this._ensureRootAttached();
        if (this._config && this._hass) {
            this.processAndRender();
        }
    }

    disconnectedCallback() {
        this._requestStop();
    }

    calculateEntites() {
        this._entities = [];
        if (Array.isArray(this._config.entities)) {
            this._entities.push(...this._config.entities);
        }
        for (const entityId in this._hass.states) {
            if (this._config.content.includes(entityId)) {
                this._entities.push(this._hass.states[entityId].entity_id);
            }
        }
    }

    processAndRender() {
        if (!this._config || !this._hass || !this._rootElement) {
            return;
        }
        this._ensureRootAttached();

        let content = this._config.content;
        if (!this._config.ignore_line_breaks) {
            content = content.replace(/\r?\n|\r/g, "</br>");
        }
        if (this._config.do_not_parse) {
            this._requestStop();
            this.render(content);
            return;
        }
        if (!this.isConnected || !this._hass.connection) {
            this._requestStop();
            return;
        }

        const generation = ++this._subscriptionGeneration;
        this._desiredSubscription = {
            generation,
            connection: this._hass.connection,
            template: content,
        };
        this._scheduleReconcile();
    }

    _requestStop() {
        ++this._subscriptionGeneration;
        this._desiredSubscription = undefined;
        this._scheduleReconcile();
    }

    _scheduleReconcile() {
        if (this._reconcileScheduled) {
            return;
        }
        this._reconcileScheduled = true;
        this._lifecycleQueue = this._lifecycleQueue
            .then(async () => {
                this._reconcileScheduled = false;
                await this._reconcileSubscription();
            })
            .catch((error) => {
                console.error("html-template-card lifecycle failed", error);
            });
    }

    async _reconcileSubscription() {
        while (true) {
            const desired = this._desiredSubscription;
            const active = this._activeSubscription;

            if (active) {
                if (desired === active.desired) {
                    return;
                }
                try {
                    await active.unsubscribe();
                } catch (error) {
                    console.error(
                        "html-template-card unsubscribe failed; replacement blocked",
                        error,
                    );
                    return;
                }
                if (this._activeSubscription === active) {
                    this._activeSubscription = undefined;
                }
                continue;
            }

            if (!desired) {
                return;
            }

            let unsubscribe;
            try {
                unsubscribe = await desired.connection.subscribeMessage(
                    (message) => {
                        if (
                            this._desiredSubscription === desired
                            && this._subscriptionGeneration === desired.generation
                            && this.isConnected
                            && this._hass?.connection === desired.connection
                        ) {
                            this.render(message.result);
                        }
                    },
                    {type: "render_template", template: desired.template},
                    // The card owns reconnect lifecycle.  The websocket library's
                    // default auto-resubscribe can otherwise resurrect an orphan
                    // after unsubscribe is requested while the socket is down.
                    {resubscribe: false},
                );
                if (typeof unsubscribe !== "function") {
                    throw new TypeError("subscribeMessage did not return an unsubscribe function");
                }
            } catch (error) {
                console.error("html-template-card subscription failed", error);
                if (this._desiredSubscription !== desired) {
                    continue;
                }
                return;
            }

            this._activeSubscription = {desired, unsubscribe};
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

customElements.define("html-template-card", HtmlTemplateCard);
