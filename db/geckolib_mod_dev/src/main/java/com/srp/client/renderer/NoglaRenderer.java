package com.srp.client.renderer;

import com.srp.client.model.NoglaModel;
import com.srp.entity.NoglaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class NoglaRenderer extends GeoEntityRenderer<NoglaEntity> {

    public NoglaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new NoglaModel());
    }
}
