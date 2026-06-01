package com.srp.client.renderer;

import com.srp.client.model.NoglaAdaptedModel;
import com.srp.entity.NoglaAdaptedEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class NoglaAdaptedRenderer extends GeoEntityRenderer<NoglaAdaptedEntity> {

    public NoglaAdaptedRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new NoglaAdaptedModel());
    }
}
